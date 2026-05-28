#!/usr/bin/env python3
"""
Local CI/CD Pipeline Runner
Simulates bitbucket-pipelines.yml stages on localhost.

Usage:
  python run_pipeline.py              # run default pipeline (all stages)
  python run_pipeline.py --branch main     # run main-branch pipeline
  python run_pipeline.py --branch staging  # run staging pipeline
  python run_pipeline.py --stage lint      # run a single stage
  python run_pipeline.py --list            # list all stages
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# Terminal colours
# ---------------------------------------------------------------------------
C = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "green":  "\033[92m",
    "red":    "\033[91m",
    "yellow": "\033[93m",
    "cyan":   "\033[96m",
    "blue":   "\033[94m",
    "grey":   "\033[90m",
}

def color(text, *keys):
    return "".join(C[k] for k in keys) + text + C["reset"]

def banner(title):
    bar = "=" * 60
    print(f"\n{color(bar, 'blue', 'bold')}")
    print(color(f"  {title}", "blue", "bold"))
    print(f"{color(bar, 'blue', 'bold')}\n")

def step_header(name, index, total):
    print(color(f"\n[{index}/{total}] {name}", "cyan", "bold"))
    print(color("-" * 50, "grey"))

def ok(msg):  print(color(f"  PASS  {msg}", "green", "bold"))
def fail(msg): print(color(f"  FAIL  {msg}", "red", "bold"))
def info(msg): print(color(f"  INFO  {msg}", "yellow"))
def note(msg): print(color(f"        {msg}", "grey"))

# ---------------------------------------------------------------------------
# Stage runner
# ---------------------------------------------------------------------------

def run_cmd(cmd, shell=True, env=None):
    """Run a shell command, stream output, return (returncode, duration)."""
    t0 = time.time()
    merged = {**os.environ, **(env or {})}
    proc = subprocess.Popen(
        cmd, shell=shell, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, env=merged,
    )
    for line in proc.stdout:
        print(color("  | ", "grey") + line, end="")
    proc.wait()
    return proc.returncode, round(time.time() - t0, 1)


def run_stage(name, commands, index, total, env=None):
    step_header(name, index, total)
    all_ok = True
    for cmd in commands:
        note(f"$ {cmd}")
        rc, dur = run_cmd(cmd, env=env)
        if rc != 0:
            fail(f"Command failed (exit {rc}) in {dur}s")
            all_ok = False
            break
        note(f"done in {dur}s")
    return all_ok


# ---------------------------------------------------------------------------
# Pipeline stage definitions (mirrors bitbucket-pipelines.yml)
# ---------------------------------------------------------------------------

MOCK_ENV = {
    "BITBUCKET_COMMIT":       "a1b2c3d4e5f6deadbeef",
    "BITBUCKET_BRANCH":       "main",
    "GCP_PROJECT_ID":         "my-streamlit-app-123",
    "GCP_REGION":             "us-central1",
    "IMAGE_NAME":             "streamlit-dashboard",
    "CLOUD_RUN_SERVICE_NAME": "streamlit-dashboard-prod",
}

STAGES = {
    "install": {
        "name": "Install dependencies",
        "commands": [
            f"{sys.executable} -m pip install --upgrade pip --quiet",
            f"{sys.executable} -m pip install -r requirements.txt --quiet",
        ],
    },
    "lint": {
        "name": "Lint (Ruff)",
        "commands": [
            f"{sys.executable} -m pip install ruff --quiet",
            f"{sys.executable} -m ruff check streamlit_app.py enterprise_dashboard.py tests/ "
            "--select=E,F,W --output-format=github",
        ],
    },
    "test": {
        "name": "Test (pytest + coverage)",
        "commands": [
            f"{sys.executable} -m pip install pytest pytest-cov --quiet",
            f"{sys.executable} -m pytest tests/test_pipeline_demo.py "
            "--cov=. --cov-report=term-missing --cov-fail-under=60 -v",
        ],
    },
    "build": {
        "name": "Build Docker image (SIMULATED — no daemon)",
        "commands": [
            f"{sys.executable} -c \""
            "import os, datetime; "
            "sha=os.environ.get('BITBUCKET_COMMIT','local')[:8]; "
            "branch=os.environ.get('BITBUCKET_BRANCH','local'); "
            "reg='us-central1-docker.pkg.dev/my-streamlit-app-123/streamlit-dashboard'; "
            "img=f'{reg}/streamlit-dashboard:{sha}'; "
            "branch_tag=f'{reg}/streamlit-dashboard:{branch}'; "
            "print(f'[SIMULATED] docker build --cache-from {branch_tag} -t {img} -t {branch_tag} .'); "
            "print(f'[SIMULATED] docker push {img}'); "
            "print(f'[SIMULATED] docker push {branch_tag}'); "
            "open('/tmp/image.env','w').write(f'IMAGE_SHA={img}'); "
            "print(f'Image tag written: {img}')"
            "\"",
        ],
    },
    "deploy": {
        "name": "Deploy to Cloud Run (SIMULATED — no GCP credentials)",
        "commands": [
            f"{sys.executable} -c \""
            "import os; "
            "sha=open('/tmp/image.env').read().split('=',1)[1].strip() "
            "if os.path.exists('/tmp/image.env') "
            "else 'us-central1-docker.pkg.dev/my-streamlit-app-123/streamlit-dashboard/streamlit-dashboard:a1b2c3d4'; "
            "svc='streamlit-dashboard-prod'; "
            "region='us-central1'; "
            "project='my-streamlit-app-123'; "
            "print('[SIMULATED] gcloud auth activate-service-account --key-file=/tmp/sa-key.json'); "
            "print(f'[SIMULATED] gcloud config set project {project}'); "
            "print(f'[SIMULATED] gcloud run deploy {svc}'); "
            "print(f'            --image={sha}'); "
            "print(f'            --region={region}'); "
            "print(f'            --port=8501 --min-instances=1 --max-instances=10'); "
            "print(f'            --memory=1Gi --cpu=1 --concurrency=80'); "
            "print('[SIMULATED] Service URL -> https://streamlit-dashboard-prod-abc123-uc.a.run.app')"
            "\"",
        ],
    },
}

# Pipeline presets (which stages run per branch)
PIPELINES = {
    "default":  ["install", "lint", "test"],
    "main":     ["install", "lint", "test", "build", "deploy"],
    "staging":  ["install", "lint", "test", "build", "deploy"],
    "pr":       ["install", "lint", "test"],
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Local Bitbucket Pipeline Runner")
    parser.add_argument("--branch", default="default",
                        choices=list(PIPELINES.keys()),
                        help="Which branch pipeline to run (default: default)")
    parser.add_argument("--stage", default=None,
                        choices=list(STAGES.keys()),
                        help="Run a single stage only")
    parser.add_argument("--list", action="store_true",
                        help="List all stages and exit")
    args = parser.parse_args()

    if args.list:
        print(color("\nAvailable stages:", "cyan", "bold"))
        for key, s in STAGES.items():
            print(f"  {color(key, 'yellow')}  --  {s['name']}")
        print(color("\nAvailable pipelines:", "cyan", "bold"))
        for key, stages in PIPELINES.items():
            print(f"  {color(key, 'yellow')}  --  {' -> '.join(stages)}")
        return

    # Determine which stages to run
    if args.stage:
        stage_keys = [args.stage]
        pipeline_name = f"single stage: {args.stage}"
    else:
        stage_keys = PIPELINES[args.branch]
        pipeline_name = f"{args.branch} branch pipeline"

    banner(f"LOCAL PIPELINE RUNNER  |  {pipeline_name.upper()}")
    print(color(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "grey"))
    print(color(f"  Stages  : {' -> '.join(stage_keys)}", "grey"))
    print(color(f"  Commit  : {MOCK_ENV['BITBUCKET_COMMIT'][:8]} (mock)", "grey"))

    results = {}
    t_total = time.time()

    for i, key in enumerate(stage_keys, 1):
        stage = STAGES[key]
        passed = run_stage(stage["name"], stage["commands"], i, len(stage_keys), env=MOCK_ENV)
        results[key] = passed
        if not passed:
            print(color(f"\n  Pipeline halted at stage: {stage['name']}", "red", "bold"))
            break

    # Summary
    elapsed = round(time.time() - t_total, 1)
    banner("PIPELINE SUMMARY")
    for key in stage_keys:
        if key in results:
            icon = color("  PASS", "green", "bold") if results[key] else color("  FAIL", "red", "bold")
        else:
            icon = color("  SKIP", "yellow")
        print(f"{icon}  {STAGES[key]['name']}")

    all_passed = all(results.values())
    print()
    if all_passed:
        print(color(f"  Pipeline PASSED in {elapsed}s", "green", "bold"))
    else:
        print(color(f"  Pipeline FAILED after {elapsed}s", "red", "bold"))
    print()

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
