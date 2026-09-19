from __future__ import annotations

import os
import subprocess
from pathlib import Path

def main() -> None:
    print("Starting script...")
    if os.name == "nt":
        script_path = Path(__file__).resolve()
        subprocess.Popen(
            ["cmd.exe", "/k", "echo hello"],
            cwd=str(script_path.parent),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        print("Opened a new command window.", flush=True)
        return

    print("hello")


if __name__ == "__main__":
    main()