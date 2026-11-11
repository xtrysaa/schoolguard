"""Точка входа приложения SchoolGuard (python -m schoolguard или SchoolGuard.exe)."""
from __future__ import annotations

import logging
import sys
import time
import urllib.request
from logging.handlers import RotatingFileHandler

PORTS = (8765, 18765, 28765, 38765)        # если порт занят другой программой, берём следующий


def _alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=1.5) as r:
            return b'"version"' in r.read(200)
    except Exception:
        return False


def _running(port_file) -> int | None:
    """Порт уже запущенной программы (по файлу с последним портом и по списку известных портов)."""
    cand = []
    try:
        cand.append(int(port_file.read_text().strip()))
    except Exception:
        pass
    for p in cand + [p for p in PORTS if p not in cand]:
        if _alive(p):
            return p
    return None


def main():
    import os
    if "--home" in sys.argv:                # отдельная папка данных (для разработки и тестов)
        os.environ["SCHOOLGUARD_HOME"] = sys.argv[sys.argv.index("--home") + 1]
    from .store import app_dir
    from .winutil import open_window
    background = "--background" in sys.argv
    home = app_dir()
    port_file = home / "port.txt"
    ports = PORTS
    if "--port" in sys.argv:                # отдельная копия для проверки: свой порт, без поиска уже запущенной
        ports = (int(sys.argv[sys.argv.index("--port") + 1]),)
    port = None if ports is not PORTS else _running(port_file)
    if port:                            # уже запущено: просто показываем окно
        if not background:
            open_window(f"http://127.0.0.1:{port}/")
        return
    handler = RotatingFileHandler(home / "logs" / "schoolguard.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if sys.stdout is None or sys.stderr is None:      # оконное приложение без консоли
        sys.stdout = sys.stderr = open(home / "logs" / "console.log", "a", encoding="utf-8", buffering=1)
    log = logging.getLogger("schoolguard")
    try:
        from .server import Core, serve
        core = Core()
        srv = serve(core, ports)
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        port_file.write_text(str(srv.server_address[1]))
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
