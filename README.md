# PG-Interleave: Postgres Concurrency Outcome Eval

## 1. Short description

PG-Interleave tests whether LLMs can predict what PostgreSQL 17.7 actually does when concurrent transactions interleave: which steps block, which error and with what SQLSTATE, what queries return, what commits and what the table holds afterwards. Ground truth comes from executing every schedule against a pinned Postgres, never from hand-written answers. **Key finding:** frontier models nearly saturate the set. Claude Opus 5.5 strictly passed 99.1% of trials and GPT-5.6-sol 97.2%. The one systematic frontier miss is implementation timing: GPT-5.6-sol knows a SERIALIZABLE seq scan causes a false-positive `40001`, but places it on the UPDATE instead of the COMMIT where Postgres raises it. Qwen3-4B, a small local model, scored 0.118 mean and passed nothing.

## 2. Video walkthrough

[Watch the narrated walkthrough (4:27)](__VIDEO_URL__)

It covers the problem and why it matters, how tasks are executed and graded, and the results, including where and why frontier models fail.

## 3. Domain and expertise

Backend and distributed systems, Postgres concurrency. Dhyan's prior work includes a Postgres-backed distributed job queue using SKIP LOCKED.

## 4. What it tests and why it matters

Each task gives the model a schema, seed rows, an isolation level and a numbered schedule of SQL steps across 2 or 3 sessions. It predicts, in JSON:
- each step's outcome (`ok`, `blocked_then_ok`, `error`, `blocked_then_error`) and SQLSTATE
- the rows returned by the observed steps
- which transactions commit
- the final table contents

The 22 shipped tasks cover:
- EvalPlanQual re-checks under READ COMMITTED, including LIMIT, semi-joins, partition moves, delete and re-insert, and a 3-session double re-check
- `40001` under REPEATABLE READ
- write skew under REPEATABLE READ vs SERIALIZABLE
- SSI predicate locks that depend on the query plan, and the SSI read-only anomaly
- SKIP LOCKED job claiming
- FK lock strength
- `ON CONFLICT` races
- sequence gaps
- lost updates

Backend engineers, DBAs and anyone using LLMs to review transactional code rely on this knowledge. Getting it wrong costs double charges, double-processed jobs and silent data loss.

## 5. Setup and run

Requires Docker with Compose, Python 3.9 or later, and `make`. Port 55432 on localhost must be free.

**From a clean checkout:**

```
unzip pg-interleave.zip && cd pg-interleave
make up      # pulls postgres:17.7, waits until healthy, records SELECT version()
make truth   # executes every task 20x, checks determinism, writes reference/
make test    # grader tests: references score 1.0, mutants score < 1.0
```

These three need no model access. `make venv`, run automatically, creates `.venv` from the pinned `requirements.txt`.

**Running models.** The shipped `transcripts/` already hold every graded trial. `make eval` resumes and skips trials whose transcript exists, so start a fresh run by first emptying `transcripts/`. Choose one way to reach the models:

1. **Direct APIs** with your own keys:
   ```
   export ANTHROPIC_API_KEY=...  OPENAI_API_KEY=...  GOOGLE_API_KEY=...
   make eval report CONFIG=config/models.api.yaml
   ```
2. **Subscription CLIs**, which is how the shipped results were produced (`config/models.yaml`): install and log in to `claude` (Claude Code) and `codex`, start the local model with `llama-server -hf Qwen/Qwen3-4B-GGUF:Q4_K_M --port 8088 -c 32768 --jinja`, then run `make eval report`.

`make all` runs up, truth, test, eval and report in one go with the default config.

| Command | What it does |
|---|---|
| `make up` | Starts `postgres:17.7` and waits until it is healthy |
| `make truth` | Runs each task 20 times and writes `reference/` |
| `make test` | Runs the grader tests |
| `make pilot` | 1 trial x tasks x 2 models |
| `make eval` | Full, resumable run per `config/models.yaml`, or per `CONFIG=...` |
| `make report` | Writes `results/summary.md` and `results/summary.csv` |
| `make zip` | Builds the submission zip. Fails on a `.env` file, a key pattern, or 50 MB and over |
| `make video-link URL=...` | Puts the walkthrough link into this README and rebuilds the zip |

**Providers:** each model entry in a config names its provider.
- `claude_cli` and `codex_cli` call the logged-in CLIs from an empty temporary directory. Claude runs with every tool disabled. A Codex trial that uses any tool is rejected rather than graded.
- `anthropic`, `openai` and `google` call the APIs over HTTP. They retry on 429 and 5xx responses, never on a wrong answer.
- An `openai` entry with `base_url` and `api_key_env: none` reaches a local OpenAI-compatible server.

Keys come only from environment variables. `make` also reads them from `~/.pg-interleave.env` if that file exists, which keeps them outside the repo. `.env.example` lists the variable names.

**Measured runtime:**
- Ground truth: 382 s in total over 20 runs of each task (`results/determinism.json`).
- Mean latency per trial: Claude 7.6 s, GPT-5.6-sol 14.6 s, Qwen3-4B 314.6 s on an Apple M5 Pro (from transcripts).

**Cost:** $0 out of pocket. Claude and GPT ran on subscription logins, Qwen ran locally, and the Gemini free tier was not usable. Token totals are in `results/summary.csv`. No USD figure is estimated, because the prices in `config/models.yaml` are not filled in.

## 6. Models tested and results

Run date: 2026-11-08, on PostgreSQL 17.7 (Debian 17.7-3.pgdg13+1) on aarch64.

| Model | How it ran | Temperature | Trials/task | Mean score | Strict pass rate | pass^5 | Cost per full run |
|---|---|---|---|---|---|---|---|
| `claude-opus-5-5` | `claude -p`, no tools, empty working directory | CLI default (cannot be set) | 5 (110 trials) | 0.999 | 0.991 | 0.955 | $0 (subscription) |
| `gpt-5.6-sol` | `codex exec`, read-only, empty working directory | CLI default (cannot be set) | 5 (108 of 110 trials) | 0.998 | 0.972 | 0.955 | $0 (subscription) |
| Qwen3-4B Q4_K_M | local `llama-server` | 0 | 5 (42 trials, 10 tasks) | 0.118 | 0.000 | 0.000 | $0 (local) |

Source: `results/summary.md` and `results/summary.csv`. pass@k is the share of tasks with at least one strict pass in k trials, and pass^k is the share of tasks where all k trials strictly pass.

Run notes:
- **Codex tool use:** a Codex trial that used a tool (web search or a shell command) is rejected and never graded. There were 7 rejected attempts (`results/eval_run.log`, `results/eval_topup.log`). 2 trials were still missing at the deadline, one each in t04a and t17.
- **Partial Qwen run:** Qwen3-4B was stopped after 42 trials, because about 5 minutes per trial could not finish before the deadline.
- **Gemini excluded:** the free tier returned HTTP 429 for the Pro models and 503 for the Flash models on the run date, so Gemini is not in the results.
- **Excluded task:** t18 (two upserts racing a delete) was nondeterministic in the 20-run check and does not ship (`results/determinism.json`).

## 7. Failure analysis

Every failure below links to its transcript. `results/summary.md` lists every failing trial with its component scores.

- **t04a_ssi_seqscan, GPT-5.6-sol, 3 of 4 trials** (`transcripts/openai-frontier/t04a_ssi_seqscan/1.json`). It predicts the false-positive serialization failure, but at B's `UPDATE` (step 8). Postgres reports it at B's `COMMIT` (step 10), after A commits. Commit flags and final state are right, so the score is 0.93. This is a near-miss on SSI implementation timing: the model knows the coarse predicate lock causes a conflict, but not when the dangerous structure is detected.
- **t10_sequence_gaps, Claude Opus 5.5, trial 5** (`transcripts/anthropic-frontier/t10_sequence_gaps/5.json`). The steps, commits and final state are all correct, but the `RETURNING id` rows include the `sku` column too (`[[2, "b"]]` vs `[[2]]`), giving 0.887. This is a near-miss on output fidelity, not a concurrency error.
- **t02_rr_concurrent_update, Qwen3-4B, 5 of 5 trials** (`transcripts/local-qwen3-4b/t02_rr_concurrent_update/1.json`). It predicts that B's update succeeds after waiting, which is InnoDB-style semantics. Postgres aborts it with `40001`, and the next statement fails with `25P02`.
- **Qwen3-4B, 30 of 42 trials** produced no JSON. All 30 used the whole 12,000-token budget reasoning and never answered.

## 8. Prior work and sources

- PostgreSQL documentation: Transaction Isolation, Explicit Locking, Serializable Snapshot Isolation
- Jepsen and Hermitage (Martin Kleppmann's isolation test suite) as inspiration. No tasks are copied.
- Nothing in this repo existed before the hackathon.

## 9. Grader validation

- Reference answers are executed truth from `harness/executor.py`, never hand-written.
- Determinism: all 22 shipped tasks gave identical outcomes in 20 of 20 runs. The one task that didn't (t18) was excluded (`results/determinism.json`).
- `graders/test_grader.py` checks that each reference scores 1.0 against itself and that its flipped-outcome, wrong-SQLSTATE, flipped-commit and modified-final-row mutants all score below 1.0.
- The same file checks that fenced JSON, reordered rows, `"100"` vs `100` and extra whitespace still score 1.0, that multiple guesses score 0 for that step, and that prompts never contain `why_hard`, the category, the title or the task id.
- `make test` must pass before `make eval` runs.

## 10. AI use

Dhyan S Agni designed the eval: the domain, the executor semantics, the grading rubric, and the expert hypotheses behind t01–t08 (in `CLAUDE.md`). He directed the build and the choices about which tasks to keep.

Claude (Claude Code) wrote the harness code, scaffolding, grader and tests, and drafted the task YAML: t01–t08 from Dhyan's hypotheses, and t09–t17 as new hypotheses. Each `why_hard` note is a hypothesis that was checked against executed Postgres. Claude also drafted this README's failure analysis from the transcripts and produced the demo video, with machine-generated narration.

No expected answer was written by a person or a model. All of them come from executing the schedules.

## 11. Hot take

Frontier models have learned the well-documented Postgres concurrency behaviors, even composed 3-session schedules. What they still miss is where an error is raised, not whether one is raised: SSI reports a dangerous structure at commit time. Closing that last gap means reasoning from how Postgres implements isolation, not from what isolation guarantees. Harder evals in this domain need timing-sensitive and plan-dependent cases rather than more textbook anomalies.
