import os
import sys
from pathlib import Path

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import collect_all


project_root = Path(globals().get("SPECPATH", ".")).resolve()
python_root = Path(sys.base_prefix)

if not (python_root / "Lib" / "tkinter").exists():
    local_appdata = Path(
        os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
    )
    python_root = local_appdata / "Programs" / "Python" / "Python310"

datas = [
    (str(project_root / "README.md"), "."),
    (str(project_root / "gui" / "assets"), "gui/assets"),
    (str(python_root / "Lib" / "tkinter"), "tkinter"),
    (str(python_root / "tcl"), "tcl"),
]
binaries = []
hiddenimports = []

packages_to_collect = [
    "customtkinter",
    "darkdetect",
    "PIL",
    "aiohttp",
    "bs4",
    "lxml",
    "selenium",
    "undetected_chromedriver",
]

for package_name in packages_to_collect:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package_name)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

hiddenimports += [
    "PIL._tkinter_finder",
]

binaries += [
    (str(python_root / "DLLs" / "_tkinter.pyd"), "."),
    (str(python_root / "DLLs" / "tcl86t.dll"), "."),
    (str(python_root / "DLLs" / "tk86t.dll"), "."),
]


a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(project_root / "pyi_rth_tkinter_fix.py")],
    excludes=[
        "pytest",
        "pytest_asyncio",
        "tests",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DeMark",
    icon=str(project_root / "installer_assets" / "DeMarkApp.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DeMark",
)
