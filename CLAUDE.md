# PG-Interleave: Postgres Concurrency Outcome Eval

Build context for the micro1 Eval Hackathon submission. Read this whole file before writing code.

Deadline: Nov 8, 2026, 9:15 PM PT. Solo submission by Dhyan S Agni.

---

## 1. What we are building

An eval that tests whether frontier LLMs can predict what PostgreSQL actually does when concurrent transactions interleave. The model gets:
- a schema
- seed rows
- an isolation level
- a numbered schedule of SQL steps across 2 or 3 sessions

It must predict, in JSON:
- which steps block
- which steps error, and with what SQLSTATE
- what SELECT steps return
- which transactions commit
- the final table contents

**The gap we are targeting:** models reason from textbook ANSI isolation definitions, or from MySQL/InnoDB behavior, instead of Postgres's real implementation. Examples:
- EvalPlanQual re-check under READ COMMITTED
- snapshot isolation that raises `40001` on concurrent update under REPEATABLE READ
- SSI predicate locks that depend on whether an index is used
- row-lock strength interactions with foreign keys
- SKIP LOCKED semantics

Backend engineers hit these as lost updates, double-processed jobs, and surprise serialization failures.

**Key design principle: ground truth is never hand-written.** Every expected answer comes from executing the schedule against a pinned Postgres version. The executed result is the reference solution.

---

## 2. Repo layout

```
pg-interleave/
├── CLAUDE.md                 # this file
├── README.md                 # submission README (see section 10)
├── docker-compose.yml        # postgres:17.x pinned by exact tag
├── Makefile                  # one-command targets
├── requirements.txt          # pinned versions
├── .env.example              # key NAMES only
├── config/models.yaml        # models under test + settings
├── tasks/                    # one YAML per task
│   └── t01_rc_evalplanqual.yaml
├── harness/
│   ├── executor.py           # runs a schedule against real Postgres
│   ├── ground_truth.py       # runs each task N times, checks determinism, writes reference/
│   ├── prompt.py             # renders task -> model prompt
│   ├── models.py             # provider clients
│   └── run_eval.py           # trials x models x tasks
├── graders/
│   ├── grade.py              # JSON comparison + partial credit
│   └── test_grader.py        # pytest: reference passes, mutants fail
├── reference/                # generated ground truth JSON, never shown to models
├── results/                  # per-run scores, summary.csv, summary.md
└── transcripts/              # raw prompt + raw model output per trial
```

---

## 3. Task file format (`tasks/*.yaml`)

```yaml
id: t01_rc_evalplanqual
title: READ COMMITTED UPDATE re-checks WHERE after blocking
isolation: read committed          # applied to every session
sessions: [A, B]
setup: |
  CREATE TABLE accounts (id int PRIMARY KEY, owner text, balance int);
  INSERT INTO accounts VALUES (1, 'alice', 100), (2, 'bob', 50);
schedule:
  - {step: 1, session: A, sql: "BEGIN"}
  - {step: 2, session: B, sql: "BEGIN"}
  - {step: 3, session: A, sql: "UPDATE accounts SET balance = 40 WHERE id = 1"}
  - {step: 4, session: B, sql: "UPDATE accounts SET balance = balance + 1 WHERE balance > 60"}
  - {step: 5, session: A, sql: "COMMIT"}
  - {step: 6, session: B, sql: "COMMIT"}
observe_steps: []                  # steps whose SELECT result rows are graded
final_query: "SELECT id, owner, balance FROM accounts ORDER BY id"
why_hard: >
  Expert note (written by Dhyan): B blocks on row 1, then re-evaluates the
  predicate against A's committed version. Models often apply snapshot logic
  and predict row 1 is updated.
category: rc_recheck
```

Rules for every task:
- Each session uses its own connection with autocommit off. `BEGIN` is explicit.
- Any non-default setting (e.g. `enable_seqscan`) is set in the schedule or the setup, and so it appears in the prompt.
- `why_hard` is the expert's hypothesis. The executed truth always wins. If truth contradicts `why_hard`, fix the note, not the truth.

---

## 4. Executor semantics (most important part, get this exactly right)

Definition that is also stated in every prompt:

> Steps are issued strictly in order. After issuing a step, the harness waits up to 1000 ms. If the statement has not returned by then, it is **blocked**, and the harness issues the next step. A blocked statement later either completes or errors when the lock it waits on is released. Steps of a session whose previous statement is still blocked are queued behind it.

Implementation:
- psycopg 3, one thread per session, each with a work queue.
- Record, per step:
  - `outcome`: `ok` | `blocked_then_ok` | `error` | `blocked_then_error`
  - `sqlstate`: the five-char code or null
  - `rows`: for `observe_steps` only
- After the last step: wait for all sessions to drain, with a hard 10 s cap. If anything is still hanging, mark the run invalid.
- Record per-transaction `committed: true|false`. A `COMMIT` after an error in the transaction returns ROLLBACK, so that counts as false.
- Run `final_query` on a fresh connection.
- Each run uses a fresh database (`CREATE DATABASE ... TEMPLATE template0`, then drop it) so there is no leftover state between runs.
- Use the default `deadlock_timeout` (1 s) unless a task overrides it. Log it.

---

## 5. Ground truth generation and determinism

`harness/ground_truth.py`:
- Runs every task 20 times.
- If all 20 outcomes are identical, it writes `reference/<id>.json`.
- If any differ, it marks the task **NONDETERMINISTIC** and excludes it. The 1000 ms block threshold and deadlock-victim selection are the usual culprits.
- It prints a table of task id, stable or not, and runtime.

Do not ship any nondeterministic task. Deadlock-victim tasks are especially timing-sensitive. Include one only if it passes 20/20 identical runs.

---

## 6. Prompt template (`harness/prompt.py`)

The prompt must contain everything the grader checks:
- Postgres exact version
- isolation level
- the blocking definition from section 4
- the setup SQL
- the schedule
- `observe_steps`
- `final_query`
- the exact output schema

It must also include an instruction to return only a JSON object, optionally inside a single ```json fence.

Output schema:

```json
{
  "steps": [
    {"step": 1, "outcome": "ok|blocked_then_ok|error|blocked_then_error", "sqlstate": null}
  ],
  "observed": {"7": [[1, "alice", 40]]},
  "committed": {"A": true, "B": false},
  "final_state": [[1, "alice", 40], [2, "bob", 50]]
}
```

Hard rule: no reference data, no `why_hard`, and no category label ever goes in the prompt.

---

## 7. Grader (`graders/grade.py`)

The grader is deterministic and code-based. There is no LLM judge.

Parse:
- Extract the first JSON object.
- If it is unparseable, the score is 0, recorded as `parse_error`.

Normalize:
- strings trimmed
- numbers compared as numbers
- final_state and observed rows compared as sorted multisets
- SQLSTATE uppercased

Score components (weights sum to 1.0):

| Component | Weight | Rule |
|---|---|---|
| step outcomes | 0.35 | fraction of steps with correct `outcome` and correct `sqlstate`. An error with the wrong code gets half credit. |
| committed | 0.20 | fraction of transactions correct |
| observed rows | 0.15 | per observed step, exact multiset match. If none are observed, redistribute this weight to final_state. |
| final_state | 0.30 | exact multiset match, all or nothing |

- **Strict pass:** score == 1.0. Report both mean score and strict pass rate.
- **Anti-gaming:** each step takes exactly one outcome value. Lists or multiple guesses mean that step scores 0.

`graders/test_grader.py` (must pass before any model run):
- Every `reference/*.json` scores exactly 1.0 against itself, after re-serializing through the model output schema.
- Auto-generated mutants all score < 1.0. For each task, produce:
  - one with a flipped outcome
  - one with a wrong SQLSTATE
  - one with a flipped commit
  - one with a modified final row
- Formatting variants of a correct answer still score 1.0:
  - fenced vs bare JSON
  - reordered rows
  - `"100"` vs `100`
  - extra whitespace

---

## 8. Task list (8 candidates, keep the ones that are deterministic and actually hard)

The expert hypotheses below are Dhyan's predictions. Executed truth decides.

1. **t01_rc_evalplanqual:** READ COMMITTED. A blocked UPDATE re-checks its WHERE against the newly committed row version and skips the row.
2. **t02_rr_concurrent_update:** REPEATABLE READ. The second updater of the same row gets `40001` once the first commits. Models that use MySQL InnoDB semantics predict success.
3. **t03_rr_vs_ser_write_skew:** the on-call doctors case. It succeeds under REPEATABLE READ and one transaction gets `40001` under SERIALIZABLE. Ship it as two tasks, one per level, and grade which transaction aborts and at which step.
4. **t04_ssi_index_vs_seqscan:** two SERIALIZABLE transactions touching logically disjoint rows.
   - Variant a forces a seq scan with `SET enable_seqscan = on` and a tiny table. Coarse predicate locks are expected to cause a false-positive `40001`.
   - Variant b uses an index scan (`SET enable_seqscan = off` and an index). No abort is expected.
   - Expert core of the eval: it tests implementation knowledge, not definitions.
5. **t05_skip_locked_claim:** job queue claiming. Two workers run `SELECT ... ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED` followed by updates. Include a third session with plain `SELECT ... LIMIT 1` and no lock, then UPDATE. It shows a double claim under READ COMMITTED.
6. **t06_lock_strength_fk:** session A holds `FOR UPDATE` on a parent row vs `FOR NO KEY UPDATE` (two variants). Session B inserts a child row referencing it.
   - The FK check takes `FOR KEY SHARE`.
   - It is expected to block only against `FOR UPDATE`.
7. **t07_on_conflict_race:** two concurrent `INSERT ... ON CONFLICT (k) DO UPDATE` on the same new key, plus a variant with `DO NOTHING`. Grade the blocking, the final row, and the observed `RETURNING` rows.
8. **t08_rc_read_modify_write:** application-style lost update. Both sessions `SELECT balance`, then `UPDATE ... SET balance = <literal from read>`. Contrast it with `SET balance = balance - 10`. Two tasks.

Target: 6 to 10 shipped tasks after the determinism and pilot filters.

---

## 9. Models and runs (`config/models.yaml`, `harness/run_eval.py`)

`config/models.yaml` lists provider, exact model ID, and params. Dhyan fills in the exact IDs.

Planned lineup:
- one frontier model each from Anthropic, OpenAI and Google
- one smaller or open model, to show the spread

Settings:
- Temperature 0 where the API accepts it. Reasoning models that reject temperature use their default; log that explicitly.
- Fixed max output tokens, enough for reasoning models.
- Trials: 5 per task per model.

Metrics per model:
- mean score
- strict pass rate
- pass@5 and pass^5 on the strict pass
- per-category breakdown
- token usage and USD cost estimated from usage

Each trial writes `transcripts/<model>/<task>/<trial>.json` containing:
- prompt
- raw output
- parsed JSON
- score breakdown
- timestamp
- model ID returned by the API
- latency

Resilience:
- Retry on 429/5xx with backoff.
- Never retry because of a bad answer.
- The run is resumable: skip trials whose transcript already exists.

Keys come from env vars only: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`. `.env.example` lists the names with empty values.

---

## 10. Commands (one command where possible)

```
make up            # docker compose up -d, wait for healthy
make truth         # ground_truth.py: 20x per task, writes reference/
make test          # pytest graders/
make pilot         # 1 trial x all tasks x 2 models (quick gap check)
make eval          # full run per config/models.yaml
make report        # results/summary.md + summary.csv
make all           # up, truth, test, eval, report
make zip           # builds submission zip, excludes .env, checks size < 50 MB
```

`make zip` must fail if:
- any file matches a key pattern (`sk-`, `AIza`, etc.)
- a `.env` file is present

---

## 11. README.md must contain (hackathon requirements)

1. Short description: domain, gap, key finding. Same text goes in the submission form.
2. Video walkthrough link (5 min max, public).
3. Domain and expertise: backend/distributed systems, Postgres concurrency. Dhyan's prior work includes a Postgres-backed distributed job queue using SKIP LOCKED.
4. What it tests and why it matters: who relies on this (backend engineers, DBAs, anyone using LLMs for code review of transactional code) and what failures cost (double charges, double-processed jobs, data loss).
5. Setup and run:
   - clean environment steps
   - `make all`
   - how to set keys
   - runtime and cost estimates from the actual run
6. Models tested and results:
   - exact model IDs
   - run date
   - temperature and trials
   - results table: Model, Trials/task, Mean score, Strict pass rate, pass^5, Cost per full run
   - per-task notes
7. Failure analysis: per task, which models failed, how, and a link to a representative failing transcript. Include at least one near-miss.
8. Prior work and sources:
   - Postgres docs (Transaction Isolation, Explicit Locking, SSI)
   - Jepsen / Hermitage (Kleppmann's isolation test suite) as inspiration. Disclose this; no tasks are copied.
   - State what existed before the hackathon: nothing in this repo.
9. Grader validation: reference = executed truth, determinism 20/20, mutant tests, format-variant tests.
10. AI use: say which parts Claude drafted (harness code, scaffolding) and that Dhyan wrote or reviewed every task, `why_hard` note, and the failure analysis by reading transcripts.
11. Hot take: the main failure pattern and what would close the gap.

Hard rule: every claim in the README must be backed by a file in `results/` or `transcripts/`. No numbers from memory. Write the README results section only after `make report`.

---

## 12. Build order for Claude

1. docker-compose + Makefile `up`. Postgres pinned to an exact 17.x tag; record the `SELECT version()` output.
2. `executor.py` + `t01` + `t02`. Run them and print the outcome JSON. Stop and show Dhyan the results.
3. `ground_truth.py` with the determinism check.
4. `grade.py` + `test_grader.py`. All tests green.
5. `prompt.py` + `models.py` + `run_eval.py`. Then `make pilot` on t01 to t04 with 2 models. **Stop and report pilot scores.** If the models score near 100%, tell Dhyan before adding more tasks of the same kind.
6. Remaining tasks, then `truth`, `test`, full `eval`, `report`.
7. README skeleton with TODO markers for anything that needs Dhyan's analysis. Do not invent findings.
8. `make zip`.

**Do not:**
- hand-write expected outputs
- put reference data where a model can see it
- add an LLM judge
- fabricate results or fill the README with claims not in results/
