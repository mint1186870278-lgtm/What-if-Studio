from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from urllib.request import urlopen


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_uvicorn_real_startup_smoke() -> None:
    port = _pick_free_port()
    env = os.environ.copy()
    env.setdefault("OPENAI_API_KEY", "smoke-test-key")
    env.setdefault("OPENAI_BASE_URL", "https://api.openai.com/v1")
    env.setdefault("OPENAI_MODEL", "gpt-4o-mini")

    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "src.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    try:
        deadline = time.time() + 25
        ok = False
        while time.time() < deadline:
            if proc.poll() is not None:
                output = (proc.stdout.read() if proc.stdout else "")[:4000]
                raise AssertionError(f"uvicorn exited early with code {proc.returncode}\n{output}")
            try:
                with urlopen(f"http://127.0.0.1:{port}/health", timeout=1.5) as resp:
                    body = resp.read().decode("utf-8")
                    if resp.status == 200 and "whatif-studio" in body:
                        ok = True
                        break
            except Exception:
                time.sleep(0.4)
        assert ok, "health check did not become ready in time"
    finally:
        if proc.poll() is None:
            if os.name == "nt":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
                time.sleep(0.5)
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
