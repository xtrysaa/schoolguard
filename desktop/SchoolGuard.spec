# Сборка: pyinstaller desktop/SchoolGuard.spec --noconfirm  ->  dist/SchoolGuard.exe (один файл, без консоли)
from pathlib import Path

ROOT = Path(SPECPATH).parent
datas = [
    (str(ROOT / "schoolguard" / "ui"), "schoolguard/ui"),
    (str(ROOT / "models" / "onnx" / "yolo11s-pose.onnx"), "models/onnx"),
    (str(ROOT / "models" / "sg_model.npz"), "models"),
    (str(ROOT / "assets" / "demo.mp4"), "assets"),
]
a = Analysis(
    [str(ROOT / "desktop" / "SchoolGuard.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["lap"],
    excludes=["torch", "torchvision", "ultralytics", "matplotlib", "pandas", "sklearn", "scipy", "xgboost", "streamlit",
              "tkinter", "onnx", "PIL", "IPython", "pytest", "numba", "sympy", "tensorflow", "pyarrow", "altair", "pydeck"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="SchoolGuard", console=False, upx=False,
          icon=str(ROOT / "desktop" / "icon.ico"))
