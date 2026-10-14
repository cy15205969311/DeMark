import os
import shutil
import sys
from pathlib import Path


runtime_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
bundled_tcl_root = runtime_root / "tcl"
public_runtime_root = Path(r"C:\Users\Public\DeMarkRuntime")
public_tcl_root = public_runtime_root / "tcl"

if bundled_tcl_root.exists():
    try:
        public_runtime_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(bundled_tcl_root, public_tcl_root, dirs_exist_ok=True)
        tcl_root = public_tcl_root
    except Exception:
        tcl_root = bundled_tcl_root
else:
    tcl_root = bundled_tcl_root

tcl_library = tcl_root / "tcl8.6"
tk_library = tcl_root / "tk8.6"

if tcl_library.exists():
    os.environ["TCL_LIBRARY"] = str(tcl_library)

if tk_library.exists():
    os.environ["TK_LIBRARY"] = str(tk_library)
