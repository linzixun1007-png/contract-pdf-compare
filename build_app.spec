# SPDX-License-Identifier: AGPL-3.0-only
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs

ROOT = Path(SPECPATH)
MODE = os.environ.get("CONTRACT_BUILD_MODE", "folder")
if MODE not in ("folder", "single"):
    raise ValueError("Unknown build mode")
datas = [(str(ROOT / "samples"), "samples"),
         (str(ROOT / "LICENSE"), "."),
         (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
         (str(ROOT / "licenses"), "licenses")]
binaries = collect_dynamic_libs("pymupdf")
tcl_root = os.environ.get("CONTRACT_TCL_ROOT")
if tcl_root:
    datas.extend([(str(Path(tcl_root) / "tcl8.6"), "_tcl_data"),
                  (str(Path(tcl_root) / "tk8.6"), "_tk_data")])
    dll_dir = Path(sys.base_prefix) / "DLLs"
    binaries.extend([(str(dll_dir / "tcl86t.dll"), "."),
                     (str(dll_dir / "tk86t.dll"), ".")])

a = Analysis([str(ROOT / "gui.py")], pathex=[str(ROOT)], binaries=binaries,
             datas=datas, hiddenimports=["self_test", "pymupdf", "tkinter", "tkinter.ttk"],
             excludes=["numpy", "pandas", "matplotlib", "scipy", "IPython", "pytest"],
             noarchive=False)
pyz = PYZ(a.pure)
if MODE == "folder":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="合同PDF对比",
              console=False, upx=False, debug=False)
    collection = COLLECT(exe, a.binaries, a.datas, name="合同PDF对比", upx=False)
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="合同PDF对比",
              console=False, upx=False, debug=False)
