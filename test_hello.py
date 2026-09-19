import os
import subprocess


if __name__ == "__main__":
    if os.name == "nt":
        subprocess.Popen(["cmd.exe", "/k", "echo hello"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.Popen(["bash", "-lc", "echo hello"])
