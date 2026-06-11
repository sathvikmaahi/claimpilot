"""Smoke test for production-identical container (requires Docker)."""

import shutil
import subprocess
import time
import urllib.request

import pytest


@pytest.mark.smoke
@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker not available")
def test_container_healthcheck():
    image = "agentic-ai-server:smoke-test"
    container = "agentic-ai-server-smoke"

    subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    build = subprocess.run(
        ["docker", "build", "-t", image, "."],
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr

    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container,
            "-e",
            "OTEL_ENABLED=false",
            "-e",
            "GOOGLE_API_KEY=smoke-test",
            "-p",
            "18080:8080",
            image,
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr

    try:
        for _ in range(30):
            try:
                with urllib.request.urlopen("http://127.0.0.1:18080/health", timeout=2) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(1)
        else:
            logs = subprocess.run(
                ["docker", "logs", container],
                capture_output=True,
                text=True,
            )
            pytest.fail(f"Container health never became ready:\n{logs.stdout}\n{logs.stderr}")

        with urllib.request.urlopen("http://127.0.0.1:18080/ready", timeout=2) as resp:
            assert resp.status == 200
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
