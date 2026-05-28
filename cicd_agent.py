#!/usr/bin/env python3
"""
CI/CD Agent powered by Claude Opus 4.7

Runs the local pipeline, detects failures, invokes Claude (with adaptive
thinking + tool use) to diagnose root causes, applies surgical fixes, and
retries failed stages automatically.

Usage:
  python cicd_agent.py                       # full default pipeline
  python cicd_agent.py --branch main         # main-branch pipeline
  python cicd_agent.py --stage lint          # single stage
  python cicd_agent.py --max-retries 5       # override retry limit

Required:
  ANTHROPIC_API_KEY environment variable must be set.
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Color helpers (ASCII-only safe for Windows cp1252 consoles)
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
    "purple": "\033[95m",
}

def color(text, *keys):
    return "".join(C[k] for k in keys) + text + C["reset"]

def banner(title):
    bar = "=" * 64
    print(f"\n{color(bar, 'blue', 'bold')}")
    print(color(f"  {title}", "blue", "bold"))
    print(f"{color(bar, 'blue', 'bold')}\n")

def ok(msg):    print(color(f"  PASS   {msg}", "green", "bold"))
def fail(msg):  print(color(f"  FAIL   {msg}", "red", "bold"))
def info(msg):  print(color(f"  INFO   {msg}", "yellow"))
def note(msg):  print(color(f"         {msg}", "grey"))
def agnt(msg):  print(color(f"  AGENT  {msg}", "purple", "bold"))

# ---------------------------------------------------------------------------
# Stage definitions (mirrors bitbucket-pipelines.yml)
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
            (
                f"{sys.executable} -m ruff check "
                "streamlit_app.py enterprise_dashboard.py tests/ "
                "--select=E,F,W --output-format=github"
            ),
        ],
    },
    "test": {
        "name": "Test (pytest + coverage)",
        "commands": [
            f"{sys.executable} -m pip install pytest pytest-cov --quiet",
            (
                f"{sys.executable} -m pytest tests/test_pipeline_demo.py "
                "--cov=. --cov-report=term-missing --cov-fail-under=60 -v"
            ),
        ],
    },
    "build": {
        "name": "Build Docker image (SIMULATED)",
        "commands": [
            (
                f"{sys.executable} -c \""
                "import os; sha=os.environ.get('BITBUCKET_COMMIT','local')[:8]; "
                "reg='us-central1-docker.pkg.dev/my-streamlit-app-123/streamlit-dashboard'; "
                "img=f'{reg}/streamlit-dashboard:{sha}'; "
                "print(f'[SIMULATED] docker build -t {img} .'); "
                "print(f'[SIMULATED] docker push {img}'); "
                "open('/tmp/image.env','w').write(f'IMAGE_SHA={img}'); "
                "print(f'Image tag: {img}')"
                "\""
            ),
        ],
    },
    "deploy": {
        "name": "Deploy to Cloud Run (SIMULATED)",
        "commands": [
            (
                f"{sys.executable} -c \""
                "import os; "
                "sha=open('/tmp/image.env').read().split('=',1)[1].strip() "
                "if os.path.exists('/tmp/image.env') "
                "else 'us-central1-docker.pkg.dev/.../streamlit-dashboard:a1b2c3d4'; "
                "print('[SIMULATED] gcloud run deploy streamlit-dashboard-prod'); "
                "print(f'  --image={sha}'); "
                "print('  --region=us-central1 --port=8501'); "
                "print('Service -> https://streamlit-dashboard-prod-abc123-uc.a.run.app')"
                "\""
            ),
        ],
    },
}

PIPELINES = {
    "default":  ["install", "lint", "test"],
    "main":     ["install", "lint", "test", "build", "deploy"],
    "staging":  ["install", "lint", "test", "build", "deploy"],
    "pr":       ["install", "lint", "test"],
}

BASE_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Stage runner — captures output and returns it
# ---------------------------------------------------------------------------

def run_stage(stage_key: str) -> tuple[bool, str]:
    """Run a pipeline stage. Returns (passed, combined_output)."""
    if stage_key not in STAGES:
        return False, f"Unknown stage: {stage_key}"

    stage = STAGES[stage_key]
    merged_env = {**os.environ, **MOCK_ENV}
    output_parts = []

    for cmd in stage["commands"]:
        output_parts.append(f"$ {cmd}\n")
        try:
            proc = subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                env=merged_env,
                cwd=str(BASE_DIR),
            )
            stdout, _ = proc.communicate()
            output_parts.append(stdout)
            if proc.returncode != 0:
                output_parts.append(f"\n[EXIT CODE {proc.returncode}]\n")
                return False, "".join(output_parts)
        except Exception as exc:
            output_parts.append(f"\n[ERROR] {exc}\n")
            return False, "".join(output_parts)

    return True, "".join(output_parts)

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_run_pipeline_stage(stage: str) -> dict:
    agnt(f"Running pipeline stage: {stage}")
    passed, output = run_stage(stage)
    return {
        "stage": stage,
        "status": "PASSED" if passed else "FAILED",
        "output": output[:5000],
    }


def tool_read_file(path: str) -> dict:
    try:
        full = (BASE_DIR / path).resolve()
        if not str(full).startswith(str(BASE_DIR)):
            return {"error": "Path outside project directory"}
        content = full.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": content, "lines": content.count("\n") + 1}
    except FileNotFoundError:
        return {"error": f"File not found: {path}"}
    except Exception as exc:
        return {"error": str(exc)}


def tool_write_file(path: str, content: str) -> dict:
    try:
        full = (BASE_DIR / path).resolve()
        if not str(full).startswith(str(BASE_DIR)):
            return {"error": "Path outside project directory"}
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        return {"status": "written", "path": path, "bytes": len(content.encode())}
    except Exception as exc:
        return {"error": str(exc)}


def tool_list_files(directory: str = ".", pattern: str = "*") -> dict:
    try:
        base = (BASE_DIR / directory).resolve()
        matches = [
            str(Path(p).relative_to(BASE_DIR))
            for p in glob.glob(str(base / "**" / pattern), recursive=True)
            if Path(p).is_file()
        ]
        return {"directory": directory, "pattern": pattern, "files": sorted(matches)[:100]}
    except Exception as exc:
        return {"error": str(exc)}


def tool_run_command(command: str) -> dict:
    blocked = ["rm -rf /", "format c:", "del /f /s", "shutdown", ":(){", "mkfs"]
    for b in blocked:
        if b in command.lower():
            return {"error": f"Blocked command pattern: {b}"}
    try:
        proc = subprocess.run(
            command, shell=True,
            capture_output=True,
            encoding="utf-8", errors="replace",
            timeout=60, cwd=str(BASE_DIR),
            env={**os.environ, **MOCK_ENV},
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout[:3000],
            "stderr": proc.stderr[:1000],
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out after 60s"}
    except Exception as exc:
        return {"error": str(exc)}


def tool_search_in_file(path: str, pattern: str) -> dict:
    try:
        full = (BASE_DIR / path).resolve()
        content = full.read_text(encoding="utf-8", errors="replace")
        regex = re.compile(pattern)
        matches = [
            {"line": i, "text": line}
            for i, line in enumerate(content.splitlines(), 1)
            if regex.search(line)
        ]
        return {"path": path, "pattern": pattern, "matches": matches[:50]}
    except FileNotFoundError:
        return {"error": f"File not found: {path}"}
    except re.error as exc:
        return {"error": f"Invalid regex: {exc}"}
    except Exception as exc:
        return {"error": str(exc)}


TOOL_MAP = {
    "run_pipeline_stage": tool_run_pipeline_stage,
    "read_file":          tool_read_file,
    "write_file":         tool_write_file,
    "list_files":         tool_list_files,
    "run_command":        tool_run_command,
    "search_in_file":     tool_search_in_file,
}

# ---------------------------------------------------------------------------
# Tool schemas for Claude
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "run_pipeline_stage",
        "description": (
            "Run a specific CI/CD pipeline stage and return its output and pass/fail status. "
            "Always call this after applying a fix to verify the stage now passes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "stage": {
                    "type": "string",
                    "enum": list(STAGES.keys()),
                    "description": "The pipeline stage to execute.",
                },
            },
            "required": ["stage"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the full contents of a file in the project directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from the project root, e.g. 'streamlit_app.py'.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write or overwrite a file in the project directory with new content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from the project root.",
                },
                "content": {
                    "type": "string",
                    "description": "The complete new content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in the project matching a glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory to search (relative to project root). Default: '.'",
                    "default": ".",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern, e.g. '*.py', '*.yml'. Default: '*'",
                    "default": "*",
                },
            },
            "required": [],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Run an arbitrary shell command in the project directory. "
            "Use for quick checks like 'python -m ruff check file.py --fix' or "
            "'python -m pytest tests/ -x'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "search_in_file",
        "description": "Search for a regex pattern in a file and return matching lines with line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Python regex pattern to search for.",
                },
            },
            "required": ["path", "pattern"],
        },
    },
]

# ---------------------------------------------------------------------------
# System prompt (cached — stable across agent invocations)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert CI/CD engineer and Python developer. Your job is to diagnose \
pipeline failures, identify root causes by reading and searching project files, \
and apply the minimal fix needed to make the failing stage pass.

Pipeline stages available:
- install : pip install from requirements.txt
- lint    : Ruff static analysis (E, F, W rules) on Python source files
- test    : pytest with 60% coverage threshold
- build   : Docker image build (simulated)
- deploy  : Cloud Run deployment (simulated)

Rules you must follow:
1. Read the failure output carefully. Find the exact error line(s).
2. Use read_file and search_in_file to understand the code at the failure point.
3. Apply the MINIMAL targeted fix with write_file. Do not rewrite whole files.
4. NEVER change test assertions to force tests to pass artificially.
5. After applying a fix, always call run_pipeline_stage to verify it passes.
6. If you cannot fix the issue, clearly explain what is wrong and why.
7. Prefer using run_command with --fix flags (e.g. ruff --fix) over manual edits.
"""

# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def execute_tool(name: str, input_args: dict) -> str:
    fn = TOOL_MAP.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    result = fn(**input_args)
    return json.dumps(result, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Agentic loop — Claude diagnoses and fixes a failed stage
# ---------------------------------------------------------------------------

def run_agent_fix(
    client: anthropic.Anthropic,
    stage: str,
    failure_output: str,
    attempt: int,
) -> bool:
    """
    Invoke Claude Opus 4.7 to fix a failed pipeline stage.
    Returns True if Claude's tool loop verifies the stage passes.
    """
    agnt(f"Claude diagnosing '{stage}' failure (attempt {attempt})...")
    print()

    messages = [
        {
            "role": "user",
            "content": (
                f"Pipeline stage `{stage}` FAILED.\n\n"
                f"Stage output:\n```\n{failure_output[:3500]}\n```\n\n"
                f"Diagnose the root cause, fix it, then call "
                f"`run_pipeline_stage` with stage=`{stage}` to confirm it passes."
            ),
        }
    ]

    last_tool_stage_passed = False

    while True:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=TOOLS,
            messages=messages,
        )

        # Print any text Claude outputs (skip thinking blocks)
        for block in response.content:
            if hasattr(block, "type") and block.type == "text" and block.text.strip():
                for line in block.text.strip().splitlines():
                    note(f"  Claude: {line}")

        # Collect tool calls from this response
        tool_calls = [b for b in response.content if hasattr(b, "type") and b.type == "tool_use"]

        # No more tool calls — Claude is done
        if response.stop_reason == "end_turn" or not tool_calls:
            break

        # Append Claude's full response to history (including thinking blocks)
        messages.append({"role": "assistant", "content": response.content})

        # Execute tools and collect results
        tool_results = []
        for tc in tool_calls:
            input_preview = json.dumps(tc.input, ensure_ascii=False)[:100]
            agnt(f"  Tool: {tc.name}({input_preview})")

            result_str = execute_tool(tc.name, tc.input)
            result_obj = json.loads(result_str)

            # Print key outcome info
            if tc.name == "run_pipeline_stage":
                status = result_obj.get("status", "?")
                if status == "PASSED":
                    ok(f"  Stage '{result_obj.get('stage')}' -> PASSED")
                    last_tool_stage_passed = True
                else:
                    fail(f"  Stage '{result_obj.get('stage')}' -> FAILED")
                    last_tool_stage_passed = False
            elif tc.name == "write_file":
                path = result_obj.get("path") or result_obj.get("error", "")
                info(f"  Written: {path}")
            elif tc.name == "run_command":
                rc = result_obj.get("returncode", "?")
                note(f"  Command exit code: {rc}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result_str,
            })

        messages.append({"role": "user", "content": tool_results})

    return last_tool_stage_passed

# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Claude Opus 4.7 CI/CD Agent")
    parser.add_argument("--branch", default="default", choices=list(PIPELINES.keys()),
                        help="Branch pipeline to run (default: default)")
    parser.add_argument("--stage", default=None, choices=list(STAGES.keys()),
                        help="Run only a single stage")
    parser.add_argument("--max-retries", type=int, default=3,
                        help="Max agent fix attempts per stage (default: 3)")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(color("\n  ERROR  ANTHROPIC_API_KEY is not set.", "red", "bold"))
        print(color("  Run: set ANTHROPIC_API_KEY=sk-ant-...", "yellow"))
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    stage_keys = [args.stage] if args.stage else PIPELINES[args.branch]
    pipeline_name = (
        f"single stage: {args.stage}" if args.stage else f"{args.branch} pipeline"
    )

    banner(f"CLAUDE CI/CD AGENT  |  {pipeline_name.upper()}")
    print(color("  Model   : claude-opus-4-7 (adaptive thinking + tool use)", "grey"))
    print(color(f"  Stages  : {' -> '.join(stage_keys)}", "grey"))
    print(color(f"  Retries : up to {args.max_retries} agent fix(es) per stage", "grey"))
    print(color(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "grey"))

    results: dict[str, str] = {}
    t_total = time.time()

    for stage_key in stage_keys:
        stage_name = STAGES[stage_key]["name"]
        print(color(f"\n[STAGE] {stage_name}", "cyan", "bold"))
        print(color("-" * 56, "grey"))

        passed = False

        for attempt in range(args.max_retries + 1):
            if attempt > 0:
                info(f"Retrying stage after agent fix (attempt {attempt}/{args.max_retries})...")

            ok_flag, output = run_stage(stage_key)

            # Stream captured output to console
            for line in output.splitlines():
                note(line)

            if ok_flag:
                results[stage_key] = "pass" if attempt == 0 else "fixed"
                label = "PASSED" if attempt == 0 else f"FIXED after {attempt} agent fix(es)"
                ok(f"{stage_name} {label}")
                passed = True
                break

            fail(f"{stage_name} FAILED (attempt {attempt + 1})")

            if attempt < args.max_retries:
                run_agent_fix(client, stage_key, output, attempt + 1)
            else:
                results[stage_key] = "fail"
                print(color(
                    f"\n  Max retries ({args.max_retries}) exhausted. "
                    f"Pipeline halted at: {stage_name}",
                    "red", "bold",
                ))

        if not passed:
            break  # halt pipeline on unrecoverable stage failure

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    elapsed = round(time.time() - t_total, 1)
    banner("AGENT PIPELINE SUMMARY")
    print(color(f"  Model: claude-opus-4-7   Elapsed: {elapsed}s\n", "grey"))

    overall_pass = True
    for key in stage_keys:
        status = results.get(key, "skip")
        if status == "pass":
            label = color("  PASS  ", "green", "bold")
        elif status == "fixed":
            label = color("  FIXED ", "cyan", "bold")
        elif status == "fail":
            label = color("  FAIL  ", "red", "bold")
            overall_pass = False
        else:
            label = color("  SKIP  ", "yellow")
            overall_pass = False
        print(f"{label} {STAGES[key]['name']}")

    print()
    if overall_pass and results:
        print(color(f"  Pipeline PASSED in {elapsed}s", "green", "bold"))
    else:
        print(color(f"  Pipeline FAILED after {elapsed}s", "red", "bold"))
    print()

    sys.exit(0 if (overall_pass and results) else 1)


if __name__ == "__main__":
    main()
