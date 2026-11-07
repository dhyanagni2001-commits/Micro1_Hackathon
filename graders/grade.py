"""Deterministic code grader. See CLAUDE.md section 7. There is no LLM judge."""
from __future__ import annotations

import json
import re
from collections import Counter

WEIGHTS = {"steps": 0.35, "committed": 0.20, "observed": 0.15, "final_state": 0.30}
ERROR_OUTCOMES = {"error", "blocked_then_error"}
OUTCOMES = {"ok", "blocked_then_ok"} | ERROR_OUTCOMES
NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
INVALID = object()


def extract_json(text):
    """Returns the first JSON object in text, or None."""
    if not isinstance(text, str):
        return None
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def norm_cell(value):
    if isinstance(value, bool) or value is None:
        return ("v", value)
    if isinstance(value, (int, float)):
        return ("n", float(value))
    if isinstance(value, str):
        value = value.strip()
        if NUMBER.match(value):
            return ("n", float(value))
        return ("s", value)
    return ("x", json.dumps(value, sort_keys=True))


def norm_rows(rows):
    """A multiset of normalized rows, or INVALID when the shape is wrong."""
    if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
        return INVALID
    return Counter(tuple(norm_cell(c) for c in row) for row in rows)


def rows_match(got, want) -> bool:
    got = norm_rows(got)
    return got is not INVALID and got == norm_rows(want)


def norm_sqlstate(value):
    """Returns an uppercase code or None. INVALID for anything that is not one answer."""
    if value is None:
        return None
    if not isinstance(value, str):
        return INVALID
    value = value.strip().upper()
    return None if value in ("", "NULL", "NONE") else value


def score_step(model_step, want) -> float:
    if model_step is None or not isinstance(model_step, dict):
        return 0.0
    outcome = model_step.get("outcome")
    if not isinstance(outcome, str):
        return 0.0
    outcome = outcome.strip().lower()
    sqlstate = norm_sqlstate(model_step.get("sqlstate"))
    if outcome not in OUTCOMES or sqlstate is INVALID or outcome != want["outcome"]:
        return 0.0
    if sqlstate == want["sqlstate"]:
        return 1.0
    return 0.5 if want["outcome"] in ERROR_OUTCOMES else 0.0


def index_steps(steps):
    """Maps step number to its entry. A number given twice is a double guess: None."""
    index = {}
    for entry in steps if isinstance(steps, list) else []:
        if not isinstance(entry, dict):
            continue
        try:
            number = int(entry.get("step"))
        except (TypeError, ValueError):
            continue
        index[number] = None if number in index else entry
    return index


def norm_bool(value):
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return value


def grade(raw_output, reference: dict) -> dict:
    parsed = extract_json(raw_output)
    if parsed is None:
        return {"score": 0.0, "strict_pass": False, "parse_error": True,
                "components": dict.fromkeys(WEIGHTS, 0.0), "parsed": None, "step_scores": {}}

    index = index_steps(parsed.get("steps"))
    step_scores = {w["step"]: score_step(index.get(w["step"]), w) for w in reference["steps"]}
    steps_score = sum(step_scores.values()) / len(step_scores) if step_scores else 1.0

    want_committed = reference["committed"]
    got_committed = parsed.get("committed")
    got_committed = got_committed if isinstance(got_committed, dict) else {}
    committed_score = sum(
        norm_bool(got_committed.get(name)) is value for name, value in want_committed.items()
    ) / len(want_committed)

    want_observed = reference["observed"]
    got_observed = parsed.get("observed")
    got_observed = got_observed if isinstance(got_observed, dict) else {}
    observed_score = (
        sum(rows_match(got_observed.get(k), v) for k, v in want_observed.items())
        / len(want_observed) if want_observed else None
    )
    final_score = 1.0 if rows_match(parsed.get("final_state"), reference["final_state"]) else 0.0

    weights = dict(WEIGHTS)
    if observed_score is None:
        weights["final_state"] += weights.pop("observed")
    components = {"steps": steps_score, "committed": committed_score, "final_state": final_score}
    if observed_score is not None:
        components["observed"] = observed_score
    score = round(sum(weights[k] * components[k] for k in weights), 10)
    return {
        "score": score,
        "strict_pass": all(v == 1.0 for v in components.values()),
        "parse_error": False,
        "components": components,
        "weights": weights,
        "step_scores": step_scores,
        "parsed": parsed,
    }
