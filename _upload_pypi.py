#!/usr/bin/env python3
"""Upload Helios v0.2.0 to PyPI.

Usage:
  export PYPI_TOKEN='your-full-token-here'
  python _upload_pypi.py
"""
import os
import subprocess
import sys

TOKEN = os.environ.get("PYPI_TOKEN", "")
if not TOKEN:
    print("ERROR: Set PYPI_TOKEN env var first.", file=sys.stderr)
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
r = subprocess.run(
    [
        sys.executable, "-m", "twine", "upload",
        "--non-interactive",
        "--username", "__token__",
        "--password", TOKEN,
        os.path.join(HERE, "dist", "helios-0.2.0-py3-none-any.whl"),
        os.path.join(HERE, "dist", "helios-0.2.0.tar.gz"),
    ],
    capture_output=True, text=True,
)
print(r.stdout[-2000:] if len(r.stdout) > 2000 else r.stdout)
print(r.stderr[-2000:] if len(r.stderr) > 2000 else r.stderr, file=sys.stderr)
sys.exit(r.returncode)