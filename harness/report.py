"""Builds results/summary.md and summary.csv by regrading every transcript's raw output."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import yaml

from graders.grade import grade


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def cost(cfg, trials):
    prices = (cfg.get("usd_per_mtok_input"), cfg.get("usd_per_mtok_output"))
    if None in prices:
        return None
    return sum(((t["input_tokens"] or 0) * prices[0] + (t["output_tokens"] or 0) * prices[1])
               / 1e6 for t in trials)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcripts", default="transcripts")
    parser.add_argument("--out", default="results")
    args = parser.parse_args()

    config = yaml.safe_load(Path("config/models.yaml").read_text())
    configs = {m["name"]: m for m in config["models"]}
    by_model = defaultdict(lambda: defaultdict(list))
    for path in sorted(Path(args.transcripts).glob("*/*/*.json")):
        record = json.loads(path.read_text())
        reference = json.loads((Path("reference") / f"{record['task']}.json").read_text())
        record["graded"] = grade(record["raw_output"], reference)
        record["path"] = str(path)
        by_model[record["model_name"]][record["task"]].append(record)
    if not by_model:
        print("no transcripts found")
        return

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    rows, lines = [], ["# PG-Interleave results", ""]
    for name, tasks in by_model.items():
        trials = [t for ts in tasks.values() for t in ts]
        passes = [t["graded"]["strict_pass"] for t in trials]
        run_cost = cost(configs.get(name, {}), trials)
        rows.append({
            "model": name,
            "model_ids_returned": ";".join(sorted({str(t["model_id_returned"]) for t in trials})),
            "tasks": len(tasks),
            "trials_per_task": max(len(ts) for ts in tasks.values()),
            "mean_score": round(mean(t["graded"]["score"] for t in trials), 4),
            "strict_pass_rate": round(mean(passes), 4),
            "pass_at_k": round(mean(any(t["graded"]["strict_pass"] for t in ts)
                                    for ts in tasks.values()), 4),
            "pass_pow_k": round(mean(all(t["graded"]["strict_pass"] for t in ts)
                                     for ts in tasks.values()), 4),
            "parse_errors": sum(t["graded"]["parse_error"] for t in trials),
            "input_tokens": sum(t["input_tokens"] or 0 for t in trials),
            "output_tokens": sum(t["output_tokens"] or 0 for t in trials),
            "cost_usd": None if run_cost is None else round(run_cost, 4),
            "mean_latency_s": round(mean(t["latency_s"] for t in trials), 2),
            "temperatures_used": ";".join(sorted({str(t["temperature_used"]) for t in trials})),
        })
    with (out / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    lines += ["pass@k: share of tasks with at least one strict pass in k trials. "
              "pass^k: share of tasks where all k trials strictly pass. "
              "k is the trials per task column.", "",
              "| Model | Returned ID | Tasks | Trials/task | Mean score | Strict pass | pass@k | "
              "pass^k | Parse errors | Tokens in/out | Cost USD | Temperature |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['model']} | {r['model_ids_returned']} | {r['tasks']} | {r['trials_per_task']} | "
            f"{r['mean_score']:.3f} | {r['strict_pass_rate']:.3f} | {r['pass_at_k']:.3f} | "
            f"{r['pass_pow_k']:.3f} | {r['parse_errors']} | {r['input_tokens']}/{r['output_tokens']} | "
            f"{'n/a' if r['cost_usd'] is None else r['cost_usd']} | {r['temperatures_used']} |")

    names = list(by_model)
    task_ids = sorted({t for tasks in by_model.values() for t in tasks})
    lines += ["", "## Per task: mean score (strict passes/trials)", "",
              "| Task | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for task_id in task_ids:
        cells = []
        for name in names:
            ts = by_model[name].get(task_id, [])
            won = sum(t["graded"]["strict_pass"] for t in ts)
            cells.append(f"{mean(t['graded']['score'] for t in ts):.2f} ({won}/{len(ts)})"
                         if ts else "-")
        lines.append(f"| {task_id} | " + " | ".join(cells) + " |")

    lines += ["", "## Per category: mean score", "",
              "| Category | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    categories = sorted({t["category"] for tasks in by_model.values()
                         for ts in tasks.values() for t in ts})
    for category in categories:
        cells = []
        for name in names:
            ts = [t for tt in by_model[name].values() for t in tt if t["category"] == category]
            cells.append(f"{mean(t['graded']['score'] for t in ts):.2f}" if ts else "-")
        lines.append(f"| {category} | " + " | ".join(cells) + " |")

    lines += ["", "## Failing trials (for failure analysis)", "",
              "| Model | Task | Trial | Score | Components | Transcript |", "|---|---|---|---|---|---|"]
    for name in names:
        for task_id, ts in sorted(by_model[name].items()):
            for t in ts:
                if not t["graded"]["strict_pass"]:
                    parts = ", ".join(f"{k} {v:.2f}" for k, v in t["graded"]["components"].items())
                    lines.append(f"| {name} | {task_id} | {t['trial']} | "
                                 f"{t['graded']['score']:.3f} | {parts} | {t['path']} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print((out / "summary.md").read_text()[:4000])


if __name__ == "__main__":
    main()
