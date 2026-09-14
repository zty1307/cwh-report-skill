"""Timeout only a child process tree created by this invocation."""
from __future__ import annotations
import os
import signal
import subprocess


def run_scoped_command(command, *, cwd=None, env=None, stdout=None, stderr=None,
                       timeout=None, input_text=None):
    process = subprocess.Popen(
        command, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    try:
        process.communicate(input=input_text, timeout=timeout)
        return process.returncode
    except BaseException:
        # Never enumerate or terminate other sessions by executable/model name.
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=10, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        raise
