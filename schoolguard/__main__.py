"""Точка входа приложения SchoolGuard (python -m schoolguard или SchoolGuard.exe)."""
from __future__ import annotations

import logging
import sys
import time
import urllib.request
from logging.handlers import RotatingFileHandler

PORT = 8765


def _alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=1.5) as r:
            return b'"version"' in r.read(200)
    except Exception:
        return False


def main():
    import os
    if "--home" in sys.argv:                # отдельная папка данных (для разработки и тестов)
        os.environ["SCHOOLGUARD_HOME"] = sys.argv[sys.argv.index("--home") + 1]
    from .store import app_dir
    from .winutil import open_window
    background = "--background" in sys.argv
    url = f"http://127.0.0.1:{PORT}/"
    if _alive(PORT):                       # уже запущено: просто показываем окно
        if not background:
            open_window(url)
        return
    home = app_dir()
    handler = RotatingFileHandler(home / "logs" / "schoolguard.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if sys.stdout is None or sys.stderr is None:      # оконное приложение без консоли
        sys.stdout = sys.stderr = open(home / "logs" / "console.log", "a", encoding="utf-8", buffering=1)
    log = logging.getLogger("schoolguard")
    try:
        from .server import Core, serve
        core = Core()
        srv = serve(core, PORT)
        log.info("SchoolGuard запущен: %s, устройство %s", url, core.detector.device)
        if not background:
            open_window(url)
        while not core.quit.wait(1.0):
            pass
        core.shutdown()
        srv.shutdown()
        time.sleep(0.3)
    except Exception:
        log.exception("fatal")
        raise


if __name__ == "__main__":
    main()
