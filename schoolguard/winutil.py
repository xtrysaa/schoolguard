"""Мелочи Windows: окно приложения и автозапуск."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def open_window(url: str):
    """Открывает интерфейс отдельным окном без адресной строки (Edge/Chrome в режиме приложения)."""
    cands = [shutil.which("msedge"), shutil.which("chrome")]
    for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
        if base:
            cands += [str(Path(base) / "Microsoft/Edge/Application/msedge.exe"),
                      str(Path(base) / "Google/Chrome/Application/chrome.exe")]
    for exe in cands:
        if exe and Path(exe).exists():
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1280,860"],
                                 creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
                return
            except Exception:
                pass
    webbrowser.open(url)


def set_autostart(enabled: bool):
    """Запуск вместе с Windows (только для текущего пользователя, без прав администратора)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, "SchoolGuard", 0, winreg.REG_SZ, f'"{sys.executable}" --background')
        else:
            try:
                winreg.DeleteValue(k, "SchoolGuard")
            except FileNotFoundError:
                pass
