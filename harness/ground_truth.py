"""Runs every task N times, checks determinism, writes reference/. CLAUDE.md section 5."""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from harness.executor import canonical, load_tasks, run_schedule, server_version


def check_task(task: dict, runs: int) -> dict:
    variants, invalid, started = {}, 0, time.monotonic()
    deadlock_timeout = None
    for _ in range(runs):
        result = run_schedule(task)
        deadlock_timeout = result["deadlock_timeout"]
        if not result["valid"]:
            invalid += 1
            continue
        key = json.dumps(canonical(result, task), sort_keys=True)
        variants[key] = variants.get(key, 0) + 1
    return {
        "id": task["id"],
        "stable": invalid == 0 and len(variants) == 1,
        "invalid_runs": invalid,
        "variants": variants,
        "deadlock_timeout": deadlock_timeout,
        "runtime_s": round(time.monotonic() - started, 1),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--jobs", type=int, default=4, help="tasks run concurrently")
    parser.add_argument("--task", action="append", help="only these task ids")
    args = parser.parse_args()

    tasks = load_tasks()
    if args.task:
        tasks = [t for t in tasks if t["id"] in args.task]
    version = server_version()
    reference_dir, results_dir = Path("reference"), Path("results")
    reference_dir.mkdir(exist_ok=True)
    results_dir.mkdir(exist_ok=True)
    Path("config/pg_version.txt").write_text(version + "\n")

    with ThreadPoolExecutor(args.jobs) as pool:
        checks = list(pool.map(lambda t: check_task(t, args.runs), tasks))

    print(version)
    print(f"{'task':34} {'status':18} {'runs':>5} {'seconds':>8}")
    for check in checks:
        path = reference_dir / f"{check['id']}.json"
        if check["stable"]:
            truth = json.loads(next(iter(check["variants"])))
            truth["meta"] = {"id": check["id"], "pg_version": version, "runs": args.runs,
                             "deadlock_timeout": check["deadlock_timeout"]}
            path.write_text(json.dumps(truth, indent=1) + "\n")
        elif path.exists():
            path.unlink()
        status = "stable" if check["stable"] else "NONDETERMINISTIC"
        print(f"{check['id']:34} {status:18} {args.runs:>5} {check['runtime_s']:>8}")

    summary_path = results_dir / "determinism.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    if not args.task:
        summary = {}
    for check in checks:
        summary[check["id"]] = {
            "stable": check["stable"], "runs": args.runs,
            "invalid_runs": check["invalid_runs"],
            "distinct_outcomes": len(check["variants"]),
            "variant_counts": list(check["variants"].values()),
            "runtime_s": check["runtime_s"], "pg_version": version,
        }
    summary_path.write_text(json.dumps(summary, indent=1) + "\n")


if __name__ == "__main__":
    main()
