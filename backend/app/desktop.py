"""Run the local app inside a native Windows WebView2 window."""

from __future__ import annotations

import logging
import os
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_desktop_logging() -> Path:
    data_dir = Path(
        os.environ.get("KODKON_DATA_DIR")
        or Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "KodKonStudio"
    ).expanduser()
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "desktop.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")],
        force=True,
    )
    return log_path


def show_error(message: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "กดก่อนคิดทีหลัง Studio", 0x10)
    except Exception:
        logging.getLogger(__name__).exception("Could not display desktop error dialog")


def run_desktop() -> None:
    logger = logging.getLogger("kodkon.desktop")

    import uvicorn
    import webview

    from app.config import settings
    from app.main import app

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=8765,
            log_config=None,
            access_log=False,
            server_header=False,
        )
    )
    server_errors: list[BaseException] = []

    def serve() -> None:
        try:
            server.run()
        except BaseException as exc:
            server_errors.append(exc)

    backend_thread = threading.Thread(target=serve, name="kodkon-local-api", daemon=True)
    backend_thread.start()

    deadline = time.monotonic() + 60
    while not server.started:
        if not backend_thread.is_alive():
            detail = str(server_errors[-1]) if server_errors else "พอร์ต 8765 อาจถูกใช้งานอยู่แล้ว"
            raise RuntimeError(f"เปิดระบบเบื้องหลังไม่สำเร็จ: {detail}")
        if time.monotonic() >= deadline:
            server.should_exit = True
            backend_thread.join(timeout=5)
            raise TimeoutError("เริ่มระบบเบื้องหลังไม่ทันเวลา")
        time.sleep(0.1)

    logger.info("Desktop window is opening; data directory: %s", settings.data_dir)
    webview.create_window(
        "กดก่อนคิดทีหลัง Studio",
        f"http://127.0.0.1:8765/?v={settings.app_version}",
        width=1440,
        height=920,
        min_size=(980, 680),
        background_color="#f4f6f8",
    )
    try:
        app_icon = Path(__file__).resolve().parents[2] / "frontend" / "public" / "kodkon-studio.ico"
        webview.start(
            gui="edgechromium",
            debug=False,
            private_mode=False,
            storage_path=str(settings.data_dir / "webview-profile"),
            icon=str(app_icon) if app_icon.is_file() else None,
        )
    finally:
        server.should_exit = True
        backend_thread.join(timeout=30)
        if backend_thread.is_alive():
            logger.warning("Local API did not stop within 30 seconds")


def main() -> int:
    log_path = configure_desktop_logging()
    try:
        run_desktop()
        return 0
    except Exception as exc:
        logging.getLogger("kodkon.desktop").exception("Desktop application stopped unexpectedly")
        show_error(
            "เปิดโปรแกรมไม่สำเร็จ\n\n"
            f"{exc}\n\n"
            f"ดูรายละเอียดได้ที่\n{log_path}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
