# PG-Interleave results

pass@k: share of tasks with at least one strict pass in k trials. pass^k: share of tasks where all k trials strictly pass. k is the trials per task column.

| Model | Returned ID | Tasks | Trials/task | Mean score | Strict pass | pass@k | pass^k | Parse errors | Tokens in/out | Cost USD | Temperature |
|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic-frontier | claude-opus-5-5 | 22 | 5 | 0.999 | 0.991 | 1.000 | 0.955 | 0 | 449835/65477 | n/a | None |
| local-qwen3-4b | Qwen/Qwen3-4B-GGUF:Q4_K_M | 10 | 5 | 0.118 | 0.000 | 0.000 | 0.000 | 30 | 35339/441398 | 0.0 | 0 |
| openai-frontier | None | 22 | 5 | 0.998 | 0.972 | 1.000 | 0.955 | 0 | 1382234/88827 | n/a | None |

## Per task: mean score (strict passes/trials)

| Task | anthropic-frontier | local-qwen3-4b | openai-frontier |
|---|---|---|---|
| t01_rc_evalplanqual | 1.00 (5/5) | 0.48 (0/5) | 1.00 (5/5) |
| t02_rr_concurrent_update | 1.00 (5/5) | 0.26 (0/5) | 1.00 (5/5) |
| t03a_rr_write_skew | 1.00 (5/5) | 0.00 (0/5) | 1.00 (5/5) |
| t03b_ser_write_skew | 1.00 (5/5) | 0.00 (0/5) | 1.00 (5/5) |
| t04a_ssi_seqscan | 1.00 (5/5) | 0.25 (0/5) | 0.95 (1/4) |
| t04b_ssi_indexscan | 1.00 (5/5) | 0.00 (0/5) | 1.00 (5/5) |
| t05_skip_locked_claim | 1.00 (5/5) | 0.00 (0/5) | 1.00 (5/5) |
| t06a_fk_for_update | 1.00 (5/5) | 0.00 (0/5) | 1.00 (5/5) |
| t06b_fk_for_no_key_update | 1.00 (5/5) | 0.00 (0/1) | 1.00 (5/5) |
| t07a_on_conflict_update | 1.00 (5/5) | 0.00 (0/1) | 1.00 (5/5) |
| t07b_on_conflict_nothing | 1.00 (5/5) | - | 1.00 (5/5) |
| t08a_rmw_literal | 1.00 (5/5) | - | 1.00 (5/5) |
| t08b_rmw_relative | 1.00 (5/5) | - | 1.00 (5/5) |
| t09_rc_lock_limit_recheck | 1.00 (5/5) | - | 1.00 (5/5) |
| t10_sequence_gaps | 0.98 (4/5) | - | 1.00 (5/5) |
| t11_rc_partition_move | 1.00 (5/5) | - | 1.00 (5/5) |
| t12_rr_select_for_update | 1.00 (5/5) | - | 1.00 (5/5) |
| t13_fk_key_share_vs_key_update | 1.00 (5/5) | - | 1.00 (5/5) |
| t14_rc_epq_semijoin | 1.00 (5/5) | - | 1.00 (5/5) |
| t15_rc_delete_reinsert | 1.00 (5/5) | - | 1.00 (5/5) |
| t16_rc_three_way_recheck | 1.00 (5/5) | - | 1.00 (5/5) |
| t17_ssi_read_only_anomaly | 1.00 (5/5) | - | 1.00 (4/4) |

## Per category: mean score

| Category | anthropic-frontier | local-qwen3-4b | openai-frontier |
|---|---|---|---|
| lock_strength | 1.00 | 0.00 | 1.00 |
| lost_update | 1.00 | - | 1.00 |
| on_conflict | 1.00 | 0.00 | 1.00 |
| rc_recheck | 1.00 | 0.48 | 1.00 |
| rr_snapshot | 1.00 | 0.26 | 1.00 |
| sequences | 0.98 | - | 1.00 |
| skip_locked | 1.00 | 0.00 | 1.00 |
| ssi_implementation | 1.00 | 0.13 | 0.98 |
| write_skew | 1.00 | 0.00 | 1.00 |

## Failing trials (for failure analysis)

| Model | Task | Trial | Score | Components | Transcript |
|---|---|---|---|---|---|
| anthropic-frontier | t10_sequence_gaps | 5 | 0.887 | steps 1.00, committed 1.00, final_state 1.00, observed 0.25 | transcripts/anthropic-frontier/t10_sequence_gaps/5.json |
| local-qwen3-4b | t01_rc_evalplanqual | 1 | 0.800 | steps 1.00, committed 0.00, final_state 1.00 | transcripts/local-qwen3-4b/t01_rc_evalplanqual/1.json |
| local-qwen3-4b | t01_rc_evalplanqual | 2 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t01_rc_evalplanqual/2.json |
| local-qwen3-4b | t01_rc_evalplanqual | 3 | 0.800 | steps 1.00, committed 0.00, final_state 1.00 | transcripts/local-qwen3-4b/t01_rc_evalplanqual/3.json |
| local-qwen3-4b | t01_rc_evalplanqual | 4 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t01_rc_evalplanqual/4.json |
| local-qwen3-4b | t01_rc_evalplanqual | 5 | 0.800 | steps 1.00, committed 0.00, final_state 1.00 | transcripts/local-qwen3-4b/t01_rc_evalplanqual/5.json |
| local-qwen3-4b | t02_rr_concurrent_update | 1 | 0.263 | steps 0.75, committed 0.00, final_state 0.00, observed 0.00 | transcripts/local-qwen3-4b/t02_rr_concurrent_update/1.json |
| local-qwen3-4b | t02_rr_concurrent_update | 2 | 0.263 | steps 0.75, committed 0.00, final_state 0.00, observed 0.00 | transcripts/local-qwen3-4b/t02_rr_concurrent_update/2.json |
| local-qwen3-4b | t02_rr_concurrent_update | 3 | 0.263 | steps 0.75, committed 0.00, final_state 0.00, observed 0.00 | transcripts/local-qwen3-4b/t02_rr_concurrent_update/3.json |
| local-qwen3-4b | t02_rr_concurrent_update | 4 | 0.263 | steps 0.75, committed 0.00, final_state 0.00, observed 0.00 | transcripts/local-qwen3-4b/t02_rr_concurrent_update/4.json |
| local-qwen3-4b | t02_rr_concurrent_update | 5 | 0.263 | steps 0.75, committed 0.00, final_state 0.00, observed 0.00 | transcripts/local-qwen3-4b/t02_rr_concurrent_update/5.json |
| local-qwen3-4b | t03a_rr_write_skew | 1 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t03a_rr_write_skew/1.json |
| local-qwen3-4b | t03a_rr_write_skew | 2 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t03a_rr_write_skew/2.json |
| local-qwen3-4b | t03a_rr_write_skew | 3 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t03a_rr_write_skew/3.json |
| local-qwen3-4b | t03a_rr_write_skew | 4 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t03a_rr_write_skew/4.json |
| local-qwen3-4b | t03a_rr_write_skew | 5 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t03a_rr_write_skew/5.json |
| local-qwen3-4b | t03b_ser_write_skew | 1 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t03b_ser_write_skew/1.json |
| local-qwen3-4b | t03b_ser_write_skew | 2 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t03b_ser_write_skew/2.json |
| local-qwen3-4b | t03b_ser_write_skew | 3 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t03b_ser_write_skew/3.json |
| local-qwen3-4b | t03b_ser_write_skew | 4 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t03b_ser_write_skew/4.json |
| local-qwen3-4b | t03b_ser_write_skew | 5 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t03b_ser_write_skew/5.json |
| local-qwen3-4b | t04a_ssi_seqscan | 1 | 0.315 | steps 0.90, committed 0.00, final_state 0.00, observed 0.00 | transcripts/local-qwen3-4b/t04a_ssi_seqscan/1.json |
| local-qwen3-4b | t04a_ssi_seqscan | 2 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t04a_ssi_seqscan/2.json |
| local-qwen3-4b | t04a_ssi_seqscan | 3 | 0.315 | steps 0.90, committed 0.00, final_state 0.00, observed 0.00 | transcripts/local-qwen3-4b/t04a_ssi_seqscan/3.json |
| local-qwen3-4b | t04a_ssi_seqscan | 4 | 0.315 | steps 0.90, committed 0.00, final_state 0.00, observed 0.00 | transcripts/local-qwen3-4b/t04a_ssi_seqscan/4.json |
| local-qwen3-4b | t04a_ssi_seqscan | 5 | 0.315 | steps 0.90, committed 0.00, final_state 0.00, observed 0.00 | transcripts/local-qwen3-4b/t04a_ssi_seqscan/5.json |
| local-qwen3-4b | t04b_ssi_indexscan | 1 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t04b_ssi_indexscan/1.json |
| local-qwen3-4b | t04b_ssi_indexscan | 2 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t04b_ssi_indexscan/2.json |
| local-qwen3-4b | t04b_ssi_indexscan | 3 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t04b_ssi_indexscan/3.json |
| local-qwen3-4b | t04b_ssi_indexscan | 4 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t04b_ssi_indexscan/4.json |
| local-qwen3-4b | t04b_ssi_indexscan | 5 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t04b_ssi_indexscan/5.json |
| local-qwen3-4b | t05_skip_locked_claim | 1 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t05_skip_locked_claim/1.json |
| local-qwen3-4b | t05_skip_locked_claim | 2 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t05_skip_locked_claim/2.json |
| local-qwen3-4b | t05_skip_locked_claim | 3 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t05_skip_locked_claim/3.json |
| local-qwen3-4b | t05_skip_locked_claim | 4 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t05_skip_locked_claim/4.json |
| local-qwen3-4b | t05_skip_locked_claim | 5 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t05_skip_locked_claim/5.json |
| local-qwen3-4b | t06a_fk_for_update | 1 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t06a_fk_for_update/1.json |
| local-qwen3-4b | t06a_fk_for_update | 2 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t06a_fk_for_update/2.json |
| local-qwen3-4b | t06a_fk_for_update | 3 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t06a_fk_for_update/3.json |
| local-qwen3-4b | t06a_fk_for_update | 4 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t06a_fk_for_update/4.json |
| local-qwen3-4b | t06a_fk_for_update | 5 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t06a_fk_for_update/5.json |
| local-qwen3-4b | t06b_fk_for_no_key_update | 2 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t06b_fk_for_no_key_update/2.json |
| local-qwen3-4b | t07a_on_conflict_update | 2 | 0.000 | steps 0.00, committed 0.00, observed 0.00, final_state 0.00 | transcripts/local-qwen3-4b/t07a_on_conflict_update/2.json |
| openai-frontier | t04a_ssi_seqscan | 1 | 0.930 | steps 0.80, committed 1.00, final_state 1.00, observed 1.00 | transcripts/openai-frontier/t04a_ssi_seqscan/1.json |
| openai-frontier | t04a_ssi_seqscan | 2 | 0.930 | steps 0.80, committed 1.00, final_state 1.00, observed 1.00 | transcripts/openai-frontier/t04a_ssi_seqscan/2.json |
| openai-frontier | t04a_ssi_seqscan | 4 | 0.930 | steps 0.80, committed 1.00, final_state 1.00, observed 1.00 | transcripts/openai-frontier/t04a_ssi_seqscan/4.json |
