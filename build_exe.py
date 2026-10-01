# SPDX-License-Identifier: AGPL-3.0-only
"""Build the same application as folder and single-file distributions."""
from pathlib import Path
import argparse
import os
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="构建同一程序的两种分发形态")
    parser.add_argument("--mode", choices=["folder", "single", "both"], default="both")
    parser.add_argument("--output", default=str(root.parent / "build"))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    modes = ["folder", "single"] if args.mode == "both" else [args.mode]
    for mode in modes:
        destination = output / mode
        destination.mkdir(parents=True, exist_ok=True)
        build_env = os.environ.copy()
        build_env["CONTRACT_BUILD_MODE"] = mode
        build_env["PYINSTALLER_CONFIG_DIR"] = str(output / "cache")
        subprocess.run([sys.executable, "-m", "PyInstaller", str(root / "build_app.spec"),
                        "--noconfirm", "--clean", "--distpath", str(destination / "dist"),
                        "--workpath", str(destination / "work")], cwd=str(root), env=build_env, check=True)


if __name__ == "__main__":
    main()
