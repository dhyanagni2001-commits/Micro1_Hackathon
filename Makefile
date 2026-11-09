PYTHON ?= python3
PY := .venv/bin/python
CONFIG ?= config/models.yaml
ENV_FILE ?= $(HOME)/.pg-interleave.env
-include $(ENV_FILE)
export
.PHONY: up down venv truth test pilot eval report all zip video-link

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
	$(PY) -m harness.run_eval --config $(CONFIG) --trials 1 --max-models 2 --transcripts results/pilot/transcripts $(if $(TASKS),--tasks $(TASKS))
	$(PY) -m harness.report --config $(CONFIG) --transcripts results/pilot/transcripts --out results/pilot

eval: venv test
	$(PY) -m harness.run_eval --config $(CONFIG)

report: venv
	$(PY) -m harness.report --config $(CONFIG)

all: up truth test eval report

zip: venv
	$(PY) -m harness.make_zip

# Puts the public video link into README.md and rebuilds the zip: make video-link URL=https://...
video-link: venv
	@test -n "$(URL)" || { echo "usage: make video-link URL=https://..."; exit 1; }
	@grep -q '__VIDEO_URL__' README.md || { echo "README already has a link"; exit 1; }
	/usr/bin/sed -i '' 's|__VIDEO_URL__|$(URL)|' README.md
	$(PY) -m harness.make_zip
