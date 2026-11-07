"""Renders a task into the model prompt. Never reads reference/, why_hard, category or title."""
from __future__ import annotations

from pathlib import Path

BLOCKING_DEFINITION = (
    "Steps are issued strictly in order. After issuing a step, the harness waits up to "
    "1000 ms. If the statement has not returned by then, it is **blocked**, and the harness "
    "issues the next step. A blocked statement later either completes or errors when the "
    "lock it waits on is released. Steps of a session whose previous statement is still "
    "blocked are queued behind it."
)

SCHEMA = """{
  "steps": [
    {"step": 1, "outcome": "ok", "sqlstate": null},
    {"step": 2, "outcome": "blocked_then_error", "sqlstate": "XXXXX"}
  ],
  "observed": {"3": [[10, "text value"]]},
  "committed": {"S1": true, "S2": false},
  "final_state": [[10, "text value"], [20, "other"]]
}"""


def pg_version() -> str:
    return Path("config/pg_version.txt").read_text().strip()


def render(task: dict, version: str = None) -> str:
    version = version or pg_version()
    schedule = "\n".join(
        f"{s['step']:>3}. [{s['session']}] {s['sql']}" for s in task["schedule"]
    )
    observe = task.get("observe_steps") or []
    observe_text = ", ".join(map(str, observe)) if observe else "none (leave `observed` as {})"
    settings = ""
    if task.get("deadlock_timeout"):
        settings = f"\nNon-default setting in every session: deadlock_timeout = {task['deadlock_timeout']}\n"
    return f"""Predict exactly what PostgreSQL does when the concurrent transactions below interleave.

PostgreSQL version: {version}
Isolation level (default_transaction_isolation in every session): {task['isolation']}
Sessions: {', '.join(task['sessions'])}. Each has its own connection. Transactions begin only at an explicit BEGIN step.
Every other setting is at its default unless the setup or schedule changes it. deadlock_timeout is 1s unless stated.{settings}

## Execution model
{BLOCKING_DEFINITION}

A queued step is issued as soon as the statement ahead of it finishes, and whether it counts as blocked is measured from that moment, not from its place in the schedule.

## Setup (already committed before step 1)
```sql
{task['setup'].strip()}
```

## Schedule
```
{schedule}
```

## What to report
- `steps`: exactly one entry for every step. `outcome` is one of:
  - `ok`: returned within 1000 ms without an error
  - `blocked_then_ok`: was blocked as defined above, then completed without an error
  - `error`: raised an error within 1000 ms
  - `blocked_then_error`: was blocked as defined above, then raised an error
  `sqlstate` is the five-character SQLSTATE for an error outcome, and null otherwise.
- `observed`: rows returned by these steps, keyed by step number as a string, each row as an array in column order: {observe_text}. A step that returns no rows, or that errors, has the value [].
- `committed`: for each session, true if its transaction committed. A COMMIT that the server answers with ROLLBACK has outcome `ok` and counts as false here.
- `final_state`: rows returned by this query, run on a fresh connection after all sessions finish:
```sql
{task['final_query'].strip()}
```

## Output format
Return only a JSON object, optionally inside a single ```json fence. Give one answer for each field. Use this shape (the values show the format only and say nothing about this schedule):
```json
{SCHEMA}
```
"""
