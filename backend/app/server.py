"""HTTP backend entry point for the Electron desktop shell."""

from __future__ import annotations

import os

import uvicorn

from app.main import app


def main() -> None:
    port = int(os.environ.get("KODKON_PORT", "8765"))
    uvicorn.run(app, host="127.0.0.1", port=port, access_log=False, server_header=False)


if __name__ == "__main__":
    main()
