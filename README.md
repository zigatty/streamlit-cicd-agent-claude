# Streamlit Dashboard — CI/CD Pipeline

A Streamlit analytics dashboard with a full CI/CD pipeline targeting **Google Cloud Run** via **Bitbucket Pipelines**.

---

## Project Structure

```
.
├── streamlit_app.py          # Main Streamlit dashboard
├── enterprise_dashboard.py   # Matplotlib enterprise chart module
├── requirements.txt          # Python dependencies
│
├── bitbucket-pipelines.yml   # CI/CD pipeline (5 stages)
├── Dockerfile                # Multi-stage production container
├── .dockerignore             # Excludes secrets, caches, dev assets
├── run_pipeline.py           # Local pipeline runner (no Bitbucket needed)
├── cicd_agent.py             # Claude Opus 4.7 AI agent — auto-diagnoses & fixes failures
│
├── ruff.toml                 # Linting config (Ruff)
├── .coveragerc               # Coverage config (pytest-cov)
│
└── tests/
    └── test_pipeline_demo.py # 18 CI/CD validation tests
```

---

## Local Development

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

App runs at **http://localhost:8501**

---

## Run the Pipeline Locally

Simulates every Bitbucket stage on your machine:

```bash
# Full main-branch pipeline (install → lint → test → build → deploy)
python run_pipeline.py --branch main

# PR gate (lint + test only)
python run_pipeline.py --branch pr

# Staging pipeline
python run_pipeline.py --branch staging

# Single stage
python run_pipeline.py --stage lint
python run_pipeline.py --stage test

# List all stages and pipelines
python run_pipeline.py --list
```

---

## CI/CD Pipeline (Bitbucket Pipelines)

| Branch | Stages |
|---|---|
| Any branch | Install → Lint → Test |
| `staging` | Install → Lint → Test → Build → Deploy (staging) |
| `main` | Install → Lint → Test → Build → Deploy (production) |
| Pull request | Install → Lint → Test |
| Manual | Rollback to any commit SHA |

**GCP target:** Cloud Run (`us-central1`)  
**Image registry:** Artifact Registry (`us-central1-docker.pkg.dev`)  
**Production service:** `streamlit-dashboard-prod`  
**Staging service:** `streamlit-dashboard-staging`

### Setup

1. Create a GCP service account with these roles:
   - `roles/run.admin`
   - `roles/artifactregistry.writer`
   - `roles/iam.serviceAccountUser`

2. Base64-encode the key:
   ```bash
   base64 -w 0 sa-key.json   # Linux
   base64 -i sa-key.json     # macOS
   ```

3. Add one Bitbucket Repository Variable (**Settings → Pipelines → Repository variables**):

   | Variable | Value | Secured |
   |---|---|---|
   | `GCLOUD_SERVICE_KEY` | base64 key output | YES |

   All other values (`GCP_PROJECT_ID`, region, service names) are hardcoded in `bitbucket-pipelines.yml` — update them to match your GCP project.

4. Enable Pipelines: **Settings → Pipelines → Settings → Enable Pipelines**

---

## Docker

Build and run locally (requires Docker):

```bash
docker build -t streamlit-dashboard .
docker run -p 8501:8501 streamlit-dashboard
```

App runs at **http://localhost:8501**

---

## CI/CD Agent (Claude Opus 4.7)

`cicd_agent.py` is an AI-powered pipeline runner. When a stage fails it invokes
Claude Opus 4.7 (with adaptive thinking + tool use) to diagnose the root cause,
apply a targeted fix, and verify the fix works — automatically.

**Setup:**

```bash
pip install anthropic
set ANTHROPIC_API_KEY=sk-ant-...   # Windows
# export ANTHROPIC_API_KEY=sk-ant-...  # macOS/Linux
```

**Usage:**

```bash
# Full default pipeline (install → lint → test) with AI auto-fix
python cicd_agent.py

# Main-branch pipeline (all 5 stages)
python cicd_agent.py --branch main

# Target a single stage
python cicd_agent.py --stage lint
python cicd_agent.py --stage test

# Limit how many fix attempts Claude gets per stage
python cicd_agent.py --max-retries 2
```

**How it works:**

1. Each stage runs normally.
2. On failure, Claude reads the error, reads relevant source files, and applies the minimal fix.
3. Claude re-runs the stage to verify the fix passes.
4. If it still fails, Claude retries up to `--max-retries` times.
5. Final summary shows `PASS`, `FIXED`, or `FAIL` per stage.

---

## Tests

```bash
pip install pytest pytest-cov
pytest tests/ -v --cov=tests --cov-report=term-missing
```

18 tests covering pipeline config, Dockerfile conventions, GCP credential structure, image tag format, and Cloud Run deploy settings.
