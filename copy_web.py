"""
copy_web.py — Bundles the built web/ dist into helios/web/ at wheel-build time.

Usage (called from setup.py / build hook):
    python copy_web.py            # builds web/ first, then copies
    python copy_web.py --skip-build   # only copies existing dist/
"""

import shutil
import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_SRC = os.path.join(HERE, "web")
DIST_SRC = os.path.join(WEB_SRC, "dist")
DEST = os.path.join(HERE, "helios", "web")


def run(cmd: list[str], cwd: str | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=cwd or HERE)


def main() -> None:
    if not os.path.exists(DEST):
        os.makedirs(DEST)

    # Copy index.html + favicon regardless of build state
    for f in ["index.html"]:
        src = os.path.join(WEB_SRC, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(DEST, f))

    # Copy built assets if they exist
    if os.path.isdir(DIST_SRC):
        for item in os.listdir(DIST_SRC):
            s = os.path.join(DIST_SRC, item)
            d = os.path.join(DEST, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
        print(f"\u2713 Copied web/dist \u2192 {DEST}")
    else:
        print(f"\u26a0  web/dist not found \u2014 skipping asset copy (run 'npm run build' first)")


if __name__ == "__main__":
    skip = "--skip-build" in sys.argv
    if not skip:
        print("Building web frontend\u2026")
        try:
            run(["npm", "install"], WEB_SRC)
            run(["npm", "run", "build"], WEB_SRC)
        except subprocess.CalledProcessError as e:
            print(f"\u26a0  Build failed ({e}); copying existing dist only")
    main()