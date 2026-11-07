PYTHON ?= python3
PY := .venv/bin/python
.PHONY: up down venv truth test pilot eval report all zip

.venv/.installed: requirements.txt
	$(PYTHON) -m venv .venv
	$(PY) -m pip install -q --disable-pip-version-check -r requirements.txt
	touch $@
venv: .venv/.installed

up:
	docker compose up -d --wait
	docker compose exec -T postgres psql -U postgres -Atc "SELECT version()" | tee config/pg_version.txt

down:
	docker compose down -v

truth: venv
	$(PY) -m harness.ground_truth

test: venv
	$(PY) -m pytest -q graders

# 1 trial x tasks x the first 2 enabled models. Narrow with: make pilot TASKS=t01,t02
pilot: venv
	$(PY) -m harness.run_eval --trials 1 --max-models 2 --transcripts results/pilot/transcripts $(if $(TASKS),--tasks $(TASKS))
	$(PY) -m harness.report --transcripts results/pilot/transcripts --out results/pilot

eval: venv test
	$(PY) -m harness.run_eval

report: venv
	$(PY) -m harness.report

all: up truth test eval report

zip: venv
	$(PY) -m harness.make_zip
