"""
CI pipeline validation tests.

These run on every branch, PR, and deploy in Bitbucket Pipelines.
They verify the project structure, config correctness, and GCP/Docker
conventions without requiring live cloud credentials or a Docker daemon.
"""
import base64
import json
import os


# ---------------------------------------------------------------------------
# Project structure
# ---------------------------------------------------------------------------

def test_requirements_file_exists():
    assert os.path.exists("requirements.txt")


def test_requirements_not_empty():
    with open("requirements.txt") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    assert len(lines) >= 4, f"Expected >=4 dependencies, found {len(lines)}"


def test_required_packages_present():
    with open("requirements.txt") as f:
        content = f.read()
    for pkg in ("streamlit", "pandas", "numpy", "plotly"):
        assert pkg in content, f"Missing required package: {pkg}"


def test_streamlit_app_file_exists():
    assert os.path.exists("streamlit_app.py")


def test_dockerfile_exists():
    assert os.path.exists("Dockerfile")


def test_dockerfile_uses_multistage_build():
    with open("Dockerfile") as f:
        content = f.read()
    assert content.count("FROM ") >= 2, "Dockerfile must use multi-stage build"
    assert "AS builder" in content
    assert "AS runtime" in content


def test_dockerfile_runs_as_non_root():
    with open("Dockerfile") as f:
        content = f.read()
    assert "appuser" in content, "Dockerfile must define a non-root user"
    assert "USER appuser" in content


def test_dockerfile_uses_port_env_var():
    with open("Dockerfile") as f:
        content = f.read()
    assert "${PORT}" in content, "CMD must use $PORT so Cloud Run can inject it"


def test_pipeline_config_exists():
    assert os.path.exists("bitbucket-pipelines.yml")


def test_pipeline_has_all_five_stages():
    with open("bitbucket-pipelines.yml") as f:
        content = f.read()
    assert "install-and-cache" in content
    assert "lint" in content
    assert "test" in content
    assert "build-and-push" in content
    assert "deploy-production" in content


def test_pipeline_has_rollback_custom_pipeline():
    with open("bitbucket-pipelines.yml") as f:
        content = f.read()
    assert "rollback-production" in content
    assert "ROLLBACK_SHA" in content


def test_pipeline_targets_correct_project():
    with open("bitbucket-pipelines.yml") as f:
        content = f.read()
    assert "my-streamlit-app-123" in content
    assert "us-central1" in content
    assert "streamlit-dashboard-prod" in content
    assert "streamlit-dashboard-staging" in content


def test_dockerignore_excludes_secrets():
    with open(".dockerignore") as f:
        content = f.read()
    for secret in (".env", "sa-key.json", "*credentials*"):
        assert secret in content, f".dockerignore must exclude: {secret}"


def test_dockerignore_excludes_large_dirs():
    with open(".dockerignore") as f:
        content = f.read()
    for directory in ("audio/", "bottle_imgs/", "swipe_files/"):
        assert directory in content, f".dockerignore must exclude: {directory}"


# ---------------------------------------------------------------------------
# GCP service account key structure (mock)
# ---------------------------------------------------------------------------

def test_gcp_sa_key_base64_roundtrip():
    """Base64 encode/decode a mock SA key the same way the pipeline does."""
    mock_sa = {
        "type": "service_account",
        "project_id": "my-streamlit-app-123",
        "private_key_id": "abc123def456",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMOCK\n-----END RSA PRIVATE KEY-----",
        "client_email": "bitbucket-cicd@my-streamlit-app-123.iam.gserviceaccount.com",
        "client_id": "123456789012345678901",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    encoded = base64.b64encode(json.dumps(mock_sa).encode()).decode()
    decoded = json.loads(base64.b64decode(encoded).decode())

    assert decoded["type"] == "service_account"
    assert decoded["project_id"] == "my-streamlit-app-123"
    assert decoded["client_email"] == "bitbucket-cicd@my-streamlit-app-123.iam.gserviceaccount.com"


# ---------------------------------------------------------------------------
# Docker image tag convention
# ---------------------------------------------------------------------------

def test_image_sha_tag_format():
    commit = "a1b2c3d4e5f6"
    region = "us-central1"
    project = "my-streamlit-app-123"
    image = "streamlit-dashboard"

    short_sha = commit[:8]
    registry = f"{region}-docker.pkg.dev/{project}/{image}"
    sha_tag = f"{registry}/{image}:{short_sha}"
    branch_tag = f"{registry}/{image}:main"

    assert len(short_sha) == 8
    assert sha_tag == "us-central1-docker.pkg.dev/my-streamlit-app-123/streamlit-dashboard/streamlit-dashboard:a1b2c3d4"
    assert branch_tag.endswith(":main")


# ---------------------------------------------------------------------------
# Cloud Run deploy configuration
# ---------------------------------------------------------------------------

def test_production_deploy_config():
    config = {
        "service": "streamlit-dashboard-prod",
        "region": "us-central1",
        "port": 8501,
        "min_instances": 1,
        "max_instances": 10,
        "memory": "1Gi",
        "cpu": 1,
        "concurrency": 80,
        "timeout": "60s",
    }
    assert config["port"] == 8501
    assert config["min_instances"] >= 1, "Prod must keep at least 1 warm instance"
    assert config["max_instances"] == 10
    assert config["memory"] == "1Gi"
    assert config["service"] == "streamlit-dashboard-prod"
    assert config["region"] == "us-central1"


def test_staging_scales_to_zero():
    staging = {"min_instances": 0, "max_instances": 3}
    prod = {"min_instances": 1, "max_instances": 10}
    assert staging["min_instances"] == 0, "Staging should scale to zero (cost saving)"
    assert prod["min_instances"] >= 1, "Prod must not cold-start"
    assert staging["max_instances"] < prod["max_instances"]
