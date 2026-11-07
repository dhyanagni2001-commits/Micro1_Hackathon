"""Runs one task schedule against real Postgres. See CLAUDE.md section 4.

Sessions use psycopg's driver-level autocommit so the driver never injects its
own BEGIN. Transactions are therefore exactly the BEGIN/COMMIT steps in the
schedule, and no statement runs outside one unless the schedule says so.
"""
from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import os
import threading
import time
import uuid
from collections import deque
from pathlib import Path

import psycopg
import yaml

BLOCK_S = 1.0     # the 1000 ms block threshold stated in every prompt
GRACE_S = 0.2     # after a step returns, time for statements it released to finish
DRAIN_S = 10.0    # hard cap on sessions draining after the last step
JOIN_S = 5.0


def base_conninfo(dbname: str = "postgres") -> str:
    return (
        f"host={os.environ.get('PGHOST', 'localhost')} "
        f"port={os.environ.get('PGPORT', '55432')} "
        f"user={os.environ.get('PGUSER', 'postgres')} "
        f"password={os.environ.get('PGPASSWORD', 'postgres')} dbname={dbname}"
    )


def load_task(path) -> dict:
    task = yaml.safe_load(Path(path).read_text())
    steps = task["schedule"]
    if [s["step"] for s in steps] != list(range(1, len(steps) + 1)):
        raise ValueError(f"{task['id']}: steps must be numbered 1..n")
    for s in steps:
        if s["session"] not in task["sessions"]:
            raise ValueError(f"{task['id']}: unknown session in step {s['step']}")
    numbers = {s["step"] for s in steps}
    if not set(task.get("observe_steps") or []) <= numbers:
        raise ValueError(f"{task['id']}: observe_steps not in schedule")
    return task


def load_tasks(directory="tasks") -> list:
    return [load_task(p) for p in sorted(Path(directory).glob("*.yaml"))]


def jsonable(value):
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (dt.date, dt.datetime, dt.time, uuid.UUID)):
        return str(value)
    return value


def to_rows(rows) -> list:
    return [[jsonable(v) for v in row] for row in rows]


class Session(threading.Thread):
    def __init__(self, name, conn, observe, cond, on_done):
        super().__init__(daemon=True, name=f"session-{name}")
        self.session_name, self.conn, self.observe = name, conn, observe
        self.cond, self.on_done = cond, on_done
        self.queue = deque()
        self.current = None
        self.started_at = 0.0
        self.committed = False
        self.stopping = False
        self.pid = conn.info.backend_pid

    def run(self):
        while True:
            with self.cond:
                while not self.queue and not self.stopping:
                    self.cond.wait()
                if not self.queue:
                    return
                step = self.queue.popleft()
                self.current, self.started_at = step, time.monotonic()
                self.cond.notify_all()
            record = self._execute(step)
            with self.cond:
                self.current = None
                self.on_done(record)
                self.cond.notify_all()

    def _execute(self, step) -> dict:
        record = {"step": step["step"], "session": self.session_name,
                  "outcome": None, "sqlstate": None, "rows": None, "error": None}
        keyword = step["sql"].strip().split()[0].upper().rstrip(";")
        failed = False
        try:
            cur = self.conn.execute(step["sql"])
            if cur.description is not None and step["step"] in self.observe:
                record["rows"] = to_rows(cur.fetchall())
            elif step["step"] in self.observe:
                record["rows"] = []
            if keyword in ("COMMIT", "END"):
                self.committed = cur.statusmessage == "COMMIT"
            elif keyword in ("ROLLBACK", "ABORT"):
                self.committed = False
        except psycopg.Error as exc:
            failed = True
            if step["step"] in self.observe:
                record["rows"] = []
            record["sqlstate"] = exc.sqlstate
            record["error"] = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
            if keyword in ("COMMIT", "END"):
                self.committed = False
        elapsed = time.monotonic() - self.started_at
        record["elapsed_ms"] = round(elapsed * 1000, 1)
        blocked = elapsed >= BLOCK_S
        if failed:
            record["outcome"] = "blocked_then_error" if blocked else "error"
        else:
            record["outcome"] = "blocked_then_ok" if blocked else "ok"
        return record


def run_schedule(task: dict) -> dict:
    """Executes the schedule once on a fresh database and returns the raw result."""
    dbname = "pgi_" + uuid.uuid4().hex[:16]
    started = time.monotonic()
    admin = psycopg.connect(base_conninfo(), autocommit=True)
    admin.execute(f'CREATE DATABASE "{dbname}" TEMPLATE template0')
    sessions = {}
    try:
        with psycopg.connect(base_conninfo(dbname), autocommit=True) as setup:
            setup.execute(task["setup"])

        cond = threading.Condition()
        results = {}
        state = {"last_done": time.monotonic()}

        def on_done(record):
            results[record["step"]] = record
            state["last_done"] = time.monotonic()

        observe = set(task.get("observe_steps") or [])
        for name in task["sessions"]:
            conn = psycopg.connect(base_conninfo(dbname), autocommit=True)
            conn.execute(
                "SELECT set_config('default_transaction_isolation', %s, false)",
                (task["isolation"],),
            )
            if task.get("deadlock_timeout"):
                conn.execute(
                    "SELECT set_config('deadlock_timeout', %s, false)",
                    (task["deadlock_timeout"],),
                )
            sessions[name] = Session(name, conn, observe, cond, on_done)
        deadlock_timeout = next(iter(sessions.values())).conn.execute(
            "SHOW deadlock_timeout").fetchone()[0]
        for s in sessions.values():
            s.start()

        def settled(now) -> bool:
            for s in sessions.values():
                if s.queue and s.current is None:
                    return False       # released or newly issued, about to start
                if s.current is not None:
                    if now - s.started_at < BLOCK_S:
                        return False   # still inside its 1000 ms window
                    if now - state["last_done"] < GRACE_S:
                        return False   # may have just been released
            return True

        for step in task["schedule"]:
            with cond:
                sessions[step["session"]].queue.append(step)
                cond.notify_all()
                while not settled(time.monotonic()):
                    cond.wait(0.005)

        deadline = time.monotonic() + DRAIN_S
        with cond:
            while any(s.queue or s.current for s in sessions.values()):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                cond.wait(min(remaining, 0.05))
            hung = [s.session_name for s in sessions.values() if s.queue or s.current]

        final_rows = None
        if not hung:
            with psycopg.connect(base_conninfo(dbname), autocommit=True) as check:
                final_rows = to_rows(check.execute(task["final_query"]).fetchall())

        steps = [results.get(s["step"]) for s in task["schedule"]]
        return {
            "id": task["id"],
            "valid": not hung,
            "hung_sessions": hung,
            "deadlock_timeout": deadlock_timeout,
            "steps": steps,
            "committed": {n: s.committed for n, s in sessions.items()},
            "final_state": final_rows,
            "runtime_s": round(time.monotonic() - started, 3),
        }
    finally:
        for s in sessions.values():
            admin.execute("SELECT pg_terminate_backend(%s)", (s.pid,))
            with s.cond:
                s.stopping = True
                s.queue.clear()
                s.cond.notify_all()
        for s in sessions.values():
            if s.is_alive():
                s.join(JOIN_S)
            try:
                s.conn.close()
            except psycopg.Error:
                pass
        admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        admin.close()


def canonical(result: dict, task: dict) -> dict:
    """The graded part of a run: what must match across runs and what models predict."""
    steps = [r for r in result["steps"] if r]
    return {
        "steps": [{"step": r["step"], "outcome": r["outcome"], "sqlstate": r["sqlstate"]}
                  for r in steps],
        "observed": {str(r["step"]): r["rows"] for r in steps
                     if r["step"] in set(task.get("observe_steps") or [])},
        "committed": result["committed"],
        "final_state": result["final_state"],
    }


def server_version() -> str:
    with psycopg.connect(base_conninfo(), autocommit=True) as conn:
        return conn.execute("SELECT version()").fetchone()[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_files", nargs="+")
    args = parser.parse_args()
    print("-- " + server_version())
    for path in args.task_files:
        task = load_task(path)
        result = run_schedule(task)
        print(json.dumps({"id": task["id"], "valid": result["valid"],
                          "runtime_s": result["runtime_s"],
                          "steps": result["steps"],
                          "committed": result["committed"],
                          "final_state": result["final_state"]}, indent=1))


if __name__ == "__main__":
    main()
