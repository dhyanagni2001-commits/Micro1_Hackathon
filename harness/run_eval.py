"""Runs trials x models x tasks. Resumable: skips trials whose transcript exists."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from graders.grade import grade
from harness.executor import load_tasks
from harness.models import ProviderError, complete, key_env
from harness.prompt import pg_version, render


LIMITS = {}


def run_trial(job) -> str:
    cfg, task, reference, trial, path, version = job
    prompt = render(task, version)
    try:
        with LIMITS[cfg["name"]]:
            reply = complete(cfg, prompt)
    except (ProviderError, KeyError, ValueError, IndexError) as exc:
        print(f"FAILED {cfg['name']} {task['id']} trial {trial}: {exc}", file=sys.stderr)
        return "failed"
    graded = grade(reply["text"], reference)
    record = {
        "model_name": cfg["name"], "model_id_requested": cfg["model"],
        "task": task["id"], "category": task["category"], "trial": trial,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "prompt": prompt, "raw_output": reply["text"], "parsed": graded.pop("parsed"),
        "score": graded,
        **{k: v for k, v in reply.items() if k != "text"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=1) + "\n")
    tmp.replace(path)
    print(f"{cfg['name']:24} {task['id']:30} trial {trial} score {graded['score']:.3f}")
    return "ok"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/models.yaml")
    parser.add_argument("--trials", type=int)
    parser.add_argument("--max-models", type=int, help="use only the first N enabled models")
    parser.add_argument("--tasks", help="comma separated id prefixes, e.g. t01,t02")
    parser.add_argument("--transcripts", default="transcripts")
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text())
    models = [m for m in config["models"] if m.get("enabled", True)]
    models = models[: args.max_models] if args.max_models else models
    missing = sorted({key_env(m) for m in models
                      if key_env(m) and not os.environ.get(key_env(m))})
    placeholders = [m["name"] for m in models if "TODO" in str(m["model"])]
    if missing or placeholders or not models:
        print(f"Cannot run. Missing env vars: {missing}. Model IDs to fill in: {placeholders}.",
              file=sys.stderr)
        return 2

    tasks, references = [], {}
    for task in load_tasks():
        path = Path("reference") / f"{task['id']}.json"
        if not path.exists():
            print(f"skipping {task['id']}: no reference (nondeterministic or truth not run)")
            continue
        if args.tasks and not task["id"].startswith(tuple(args.tasks.split(","))):
            continue
        tasks.append(task)
        references[task["id"]] = json.loads(path.read_text())

    trials = args.trials or config.get("trials", 5)
    version = pg_version()
    jobs = []
    for cfg in models:
        cfg = {**config.get("defaults", {}), **cfg}
        LIMITS[cfg["name"]] = threading.Semaphore(cfg.get("max_concurrency", 3))
        for task in tasks:
            for trial in range(1, trials + 1):
                path = Path(args.transcripts) / cfg["name"] / task["id"] / f"{trial}.json"
                if not path.exists():
                    jobs.append((cfg, task, references[task["id"]], trial, path, version))
    print(f"{len(jobs)} trials to run, {len(models)} models, {len(tasks)} tasks")
    with ThreadPoolExecutor(config.get("concurrency", 6)) as pool:
        outcomes = list(pool.map(run_trial, jobs))
    failed = outcomes.count("failed")
    print(f"done, {len(outcomes) - failed} ok, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
