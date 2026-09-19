from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

def main() -> None:
    if os.name == "nt" and os.environ.get("VACNET_SCRIPT_WINDOW") != "1":
        script_path = Path(__file__).resolve()
        environment = os.environ.copy()
        environment["VACNET_SCRIPT_WINDOW"] = "1"
        subprocess.Popen(
            ["cmd.exe", "/k", sys.executable, str(script_path)],
            cwd=str(script_path.parent),
            env=environment,
        )
        return

    print("hello")


if __name__ == "__main__":
    main()