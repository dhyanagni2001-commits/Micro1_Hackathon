# PG-Interleave: Postgres Concurrency Outcome Eval

> Lines marked TODO need Dhyan's analysis or real model results. Every claim here must be backed by a file in `results/` or `transcripts/`.

## 1. Short description

Domain: backend and distributed systems, specifically PostgreSQL concurrency. Gap tested: whether LLMs predict what PostgreSQL really does when concurrent transactions interleave, or fall back on textbook ANSI isolation definitions and MySQL/InnoDB behavior.

TODO(after `make report`): key finding, one sentence. Use the same text in the submission form.

## 2. Video walkthrough

TODO: public link, 5 minutes or less.

## 3. Domain and expertise

Backend and distributed systems, Postgres concurrency. Dhyan's prior work includes a Postgres-backed distributed job queue using SKIP LOCKED.

## 4. What it tests and why it matters

Each task gives a model a schema, seed rows, an isolation level and a numbered schedule of SQL steps across 2 or 3 sessions. The model predicts which steps block, which steps error and with what SQLSTATE, what SELECT and RETURNING steps return, which transactions commit, and the final table contents.

Behaviors covered: EvalPlanQual re-checks under READ COMMITTED, `40001` on concurrent update under REPEATABLE READ, write skew, SSI predicate locks that depend on the query plan, SKIP LOCKED, row-lock strength against foreign keys, `ON CONFLICT` races and application-level lost updates.

Backend engineers, DBAs and anyone using LLMs to review transactional code rely on this knowledge. Getting it wrong costs double charges, double-processed jobs and lost data.

Ground truth is never hand-written. Every expected answer comes from executing the schedule against a pinned PostgreSQL version (`config/pg_version.txt`).

## 5. Setup and run

Requires Docker with Compose, Python 3.9 or later, and `make`.

```
export ANTHROPIC_API_KEY=...   # names are listed in .env.example
export OPENAI_API_KEY=...
export GOOGLE_API_KEY=...
# fill in exact model IDs and prices in config/models.yaml
make all
```

| Command | What it does |
|---|---|
| `make up` | Starts the pinned Postgres and waits until it is healthy |
| `make truth` | Runs each task 20 times and writes `reference/` |
| `make test` | Runs the grader tests |
| `make pilot` | 1 trial x all tasks x 2 models (`TASKS=t01,t02` narrows it) |
| `make eval` | Full, resumable run per `config/models.yaml` |
| `make report` | Writes `results/summary.md` and `results/summary.csv` |
| `make zip` | Builds the submission zip. Fails on a `.env` file, a key pattern, or 50 MB and over |

Keep keys in exported env vars. `make zip` refuses to run while a `.env` file is in the repo.

TODO(after `make eval`): measured runtime and cost.

## 6. Models tested and results

TODO(after `make report`): exact model IDs, run date, temperature, trials, then this table from `results/summary.md`:

| Model | Trials/task | Mean score | Strict pass rate | pass^5 | Cost per full run |
|---|---|---|---|---|---|
| TODO | | | | | |

TODO: per-task notes.

## 7. Failure analysis

TODO(Dhyan, from reading transcripts): per task, which models failed, how, and a link to a representative failing transcript. Include at least one near-miss. `results/summary.md` lists every failing trial with its path.

## 8. Prior work and sources

- PostgreSQL documentation: Transaction Isolation, Explicit Locking, Serializable Snapshot Isolation
- Jepsen and Hermitage (Martin Kleppmann's isolation test suite) as inspiration. No tasks are copied.
- Nothing in this repo existed before the hackathon.

## 9. Grader validation

- Reference answers are executed truth, never hand-written.
- Determinism: every shipped task produced identical outcomes across 20 of 20 runs (`results/determinism.json`).
- `graders/test_grader.py` checks that each reference scores 1.0 against itself and that its flipped-outcome, wrong-SQLSTATE, flipped-commit and modified-final-row mutants all score below 1.0.
- The same file checks that fenced JSON, reordered rows, `"100"` vs `100` and extra whitespace still score 1.0, that multiple guesses score 0 for that step, and that prompts never contain `why_hard`, the category, the title or the task id.

## 10. AI use

Claude drafted the harness code, scaffolding, grader, tests and task YAML from the hypotheses in `CLAUDE.md`.

TODO(Dhyan): confirm once done that you reviewed every task and `why_hard` note, and wrote the failure analysis by reading transcripts.

## 11. Hot take

TODO(Dhyan, after results): the main failure pattern and what would close the gap.
