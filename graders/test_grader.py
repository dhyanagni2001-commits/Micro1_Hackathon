"""Must pass before any model run. See CLAUDE.md section 7."""
import copy
import json
from pathlib import Path

import pytest

from graders.grade import grade
from harness.executor import load_tasks
from harness.prompt import render

ROOT = Path(__file__).resolve().parent.parent
REFERENCES = sorted((ROOT / "reference").glob("*.json"))
FLIP = {"ok": "blocked_then_ok", "blocked_then_ok": "ok",
        "error": "blocked_then_error", "blocked_then_error": "error"}


def answer(path):
    data = json.loads(path.read_text())
    return {k: data[k] for k in ("steps", "observed", "committed", "final_state")}


def score(output, reference):
    return grade(json.dumps(output), reference)


@pytest.fixture(params=REFERENCES, ids=lambda p: p.stem)
def ref(request):
    return answer(request.param)


def test_references_exist():
    assert REFERENCES, "run `make truth` first"


def test_reference_scores_one(ref):
    result = score(ref, ref)
    assert result["score"] == 1.0 and result["strict_pass"]


def test_mutant_flipped_outcome(ref):
    for i in range(len(ref["steps"])):
        mutant = copy.deepcopy(ref)
        mutant["steps"][i]["outcome"] = FLIP[mutant["steps"][i]["outcome"]]
        assert score(mutant, ref)["score"] < 1.0


def test_mutant_wrong_sqlstate(ref):
    for i, step in enumerate(ref["steps"]):
        mutant = copy.deepcopy(ref)
        mutant["steps"][i]["sqlstate"] = "XX000" if step["sqlstate"] else "40001"
        assert score(mutant, ref)["score"] < 1.0


def test_mutant_flipped_commit(ref):
    for name in ref["committed"]:
        mutant = copy.deepcopy(ref)
        mutant["committed"][name] = not mutant["committed"][name]
        assert score(mutant, ref)["score"] < 1.0


def test_mutant_modified_final_row(ref):
    mutant = copy.deepcopy(ref)
    if mutant["final_state"]:
        row = mutant["final_state"][0]
        row[-1] = (row[-1] + 1) if isinstance(row[-1], (int, float)) else f"{row[-1]}x"
    else:
        mutant["final_state"] = [[1]]
    assert score(mutant, ref)["score"] < 1.0


def test_mutant_extra_or_missing_final_row(ref):
    extra = copy.deepcopy(ref)
    extra["final_state"].append([999])
    assert score(extra, ref)["score"] < 1.0
    if ref["final_state"]:
        missing = copy.deepcopy(ref)
        missing["final_state"].pop()
        assert score(missing, ref)["score"] < 1.0


def test_format_fenced_json(ref):
    assert grade("```json\n" + json.dumps(ref) + "\n```", ref)["score"] == 1.0


def test_format_reordered_rows(ref):
    variant = copy.deepcopy(ref)
    variant["final_state"].reverse()
    for rows in variant["observed"].values():
        rows.reverse()
    assert score(variant, ref)["score"] == 1.0


def stringify(rows):
    return [[str(c) if isinstance(c, int) and not isinstance(c, bool) else c for c in r]
            for r in rows]


def test_format_string_numbers(ref):
    variant = copy.deepcopy(ref)
    variant["final_state"] = stringify(variant["final_state"])
    variant["observed"] = {k: stringify(v) for k, v in variant["observed"].items()}
    assert score(variant, ref)["score"] == 1.0


def pad(rows):
    return [[f"  {c} " if isinstance(c, str) else c for c in r] for r in rows]


def test_format_extra_whitespace(ref):
    variant = copy.deepcopy(ref)
    variant["final_state"] = pad(variant["final_state"])
    variant["observed"] = {k: pad(v) for k, v in variant["observed"].items()}
    assert grade("\n\n  " + json.dumps(variant, indent=4) + "  \n", ref)["score"] == 1.0


def test_sqlstate_case_is_ignored(ref):
    variant = copy.deepcopy(ref)
    for step in variant["steps"]:
        if step["sqlstate"]:
            step["sqlstate"] = step["sqlstate"].lower()
    assert score(variant, ref)["score"] == 1.0


# Rule tests on a fixed answer. These values only exercise grader arithmetic.
SAMPLE = {
    "steps": [{"step": 1, "outcome": "ok", "sqlstate": None},
              {"step": 2, "outcome": "blocked_then_error", "sqlstate": "40001"}],
    "observed": {"1": [[1, "a"]]},
    "committed": {"A": True, "B": False},
    "final_state": [[1, "a"]],
}


def test_unparseable_is_zero_parse_error():
    result = grade("I think it blocks.", SAMPLE)
    assert result["score"] == 0.0 and result["parse_error"]


def test_wrong_code_gets_half_step_credit():
    variant = copy.deepcopy(SAMPLE)
    variant["steps"][1]["sqlstate"] = "23505"
    result = score(variant, SAMPLE)
    assert result["step_scores"][2] == 0.5 and result["components"]["steps"] == 0.75


def test_wrong_outcome_gets_no_credit_even_with_right_code():
    variant = copy.deepcopy(SAMPLE)
    variant["steps"][1]["outcome"] = "error"
    assert score(variant, SAMPLE)["step_scores"][2] == 0.0


def test_gaming_list_outcome_scores_zero():
    variant = copy.deepcopy(SAMPLE)
    variant["steps"][1]["outcome"] = ["error", "blocked_then_error"]
    assert score(variant, SAMPLE)["step_scores"][2] == 0.0


def test_gaming_combined_outcome_scores_zero():
    variant = copy.deepcopy(SAMPLE)
    variant["steps"][0]["outcome"] = "ok|blocked_then_ok"
    assert score(variant, SAMPLE)["step_scores"][1] == 0.0


def test_gaming_duplicate_step_scores_zero():
    variant = copy.deepcopy(SAMPLE)
    variant["steps"].append({"step": 1, "outcome": "blocked_then_ok", "sqlstate": None})
    assert score(variant, SAMPLE)["step_scores"][1] == 0.0


def test_gaming_sqlstate_list_scores_zero():
    variant = copy.deepcopy(SAMPLE)
    variant["steps"][1]["sqlstate"] = ["40001", "40P01"]
    assert score(variant, SAMPLE)["step_scores"][2] == 0.0


def test_weights_redistribute_when_nothing_observed():
    want = dict(SAMPLE, observed={})
    variant = copy.deepcopy(want)
    variant["final_state"] = [[2, "b"]]
    assert score(variant, want)["score"] == 0.55


def test_prompts_never_leak_hidden_fields():
    for task in load_tasks(ROOT / "tasks"):
        prompt = render(task, "PostgreSQL 17.x")
        assert task["why_hard"].strip() not in prompt
        assert task["category"] not in prompt
        assert task["id"] not in prompt
        assert task["title"] not in prompt
