# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

for pkg in [
    "librosa", "soundfile", "soxr", "mido",
    "audioread", "numba", "llvmlite",
    "sklearn", "joblib", "scipy", "numpy",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# 部分套件的底層模組無法被 collect_all 完全掃到，明確補上避免啟動時 ModuleNotFoundError
hiddenimports += [
    "scipy.special.cython_special",
    "sklearn.utils._typedefs",
    "librosa.core.audio",
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.ttk",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "IPython", "notebook", "PyQt5", "PySide2", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="GrooveMap",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name="GrooveMap",
)
