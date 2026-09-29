"""Start the packaged backend against disposable data and verify its health endpoint."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "release" / "backend-bundle" / "kodkon-backend" / "kodkon-backend.exe"


def main() -> None:
    executable = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else EXE
    if not executable.is_file():
        raise RuntimeError(f"Backend bundle is missing: {executable}")
    resources = executable.parent.parent if executable != EXE else ROOT
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="kodkon-backend-smoke-") as data_dir:
        env = os.environ.copy()
        env.update(
            KODKON_DATA_DIR=data_dir,
            KODKON_PORT=str(port),
            KODKON_BACKEND_ROOT=str(resources / "backend"),
            KODKON_RESOURCE_ROOT=str(resources),
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            [str(executable)], env=env, cwd=resources / "backend", creationflags=flags,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        try:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError(f"Backend exited: {process.stderr.read().decode(errors='replace')[-3000:]}")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                        if response.status == 200:
                            print("Packaged backend health check passed")
                            return
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.5)
            raise RuntimeError("Packaged backend did not become healthy in 30 seconds")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
