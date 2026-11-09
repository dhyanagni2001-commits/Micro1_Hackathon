# PG-Interleave results

pass@k: share of tasks with at least one strict pass in k trials. pass^k: share of tasks where all k trials strictly pass. k is the trials per task column.

| Model | Returned ID | Tasks | Trials/task | Mean score | Strict pass | pass@k | pass^k | Parse errors | Tokens in/out | Cost USD | Temperature |
|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic-frontier | claude-opus-5-5 | 6 | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 24454/3871 | n/a | None |
| local-qwen3-4b | Qwen/Qwen3-4B-GGUF:Q4_K_M | 3 | 1 | 0.421 | 0.000 | 0.000 | 0.000 | 0 | 2440/17298 | 0.0 | 0 |
| openai-frontier | None | 6 | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 76765/4436 | n/a | None |

## Per task: mean score (strict passes/trials)

| Task | anthropic-frontier | local-qwen3-4b | openai-frontier |
|---|---|---|---|
| t01_rc_evalplanqual | 1.00 (1/1) | 0.35 (0/1) | 1.00 (1/1) |
| t02_rr_concurrent_update | 1.00 (1/1) | 0.26 (0/1) | 1.00 (1/1) |
| t03a_rr_write_skew | 1.00 (1/1) | 0.65 (0/1) | 1.00 (1/1) |
| t03b_ser_write_skew | 1.00 (1/1) | - | 1.00 (1/1) |
| t04a_ssi_seqscan | 1.00 (1/1) | - | 1.00 (1/1) |
| t04b_ssi_indexscan | 1.00 (1/1) | - | 1.00 (1/1) |

## Per category: mean score

| Category | anthropic-frontier | local-qwen3-4b | openai-frontier |
|---|---|---|---|
| rc_recheck | 1.00 | 0.35 | 1.00 |
| rr_snapshot | 1.00 | 0.26 | 1.00 |
| ssi_implementation | 1.00 | - | 1.00 |
| write_skew | 1.00 | 0.65 | 1.00 |

## Failing trials (for failure analysis)

| Model | Task | Trial | Score | Components | Transcript |
|---|---|---|---|---|---|
| local-qwen3-4b | t01_rc_evalplanqual | 1 | 0.350 | steps 1.00, committed 0.00, final_state 0.00 | results/pilot/transcripts/local-qwen3-4b/t01_rc_evalplanqual/1.json |
| local-qwen3-4b | t02_rr_concurrent_update | 1 | 0.263 | steps 0.75, committed 0.00, final_state 0.00, observed 0.00 | results/pilot/transcripts/local-qwen3-4b/t02_rr_concurrent_update/1.json |
| local-qwen3-4b | t03a_rr_write_skew | 1 | 0.650 | steps 1.00, committed 0.00, final_state 1.00, observed 0.00 | results/pilot/transcripts/local-qwen3-4b/t03a_rr_write_skew/1.json |
