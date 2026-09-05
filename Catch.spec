# PyInstaller build definition for Catch.
from pathlib import Path

from PyInstaller.building.build_main import Analysis, EXE, PYZ
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_root = Path(SPEC).parent
openwakeword_datas = collect_data_files("openwakeword")
openwakeword_hiddenimports = collect_submodules("openwakeword")
datas = [
    (str(project_root / "config.yaml"), "."),
    (str(project_root / "catch_idle.webm"), "."),
    (str(project_root / "catch_listening.webm"), "."),
    (str(project_root / "catch_thinking.webm"), "."),
    (str(project_root / "ready_for_hey_jarvis.mp3"), "."),
    (str(project_root / "listening.mp3"), "."),
    *openwakeword_datas,
]

analysis = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=openwakeword_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests", "benchmark_runtime", "benchmark_whisper", "test_whisper"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="Catch",
    icon=str(project_root / "CatchAI_app_logo.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
