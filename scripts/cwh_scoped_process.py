"""Timeout only a child process tree created by this invocation."""
from __future__ import annotations
import os
import signal
import subprocess
import threading
import time


def run_scoped_command(command, *, cwd=None, env=None, stdout=None, stderr=None,
                       timeout=None, input_text=None):
    communication, owned_job, job_assigned = None, None, False
    if os.name == 'nt':
        from cwh_windows_job import OwnedWindowsJob
        owned_job = OwnedWindowsJob()
    try:
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
    except BaseException:
        if owned_job is not None:
            owned_job.close()
        raise
    try:
        if owned_job is not None:
            owned_job.assign(process)
            job_assigned = True
        if timeout is None:
            process.communicate(input=input_text)
        else:
            # Windows communicate() can block while writing a large stdin
            # before it reaches its timed wait. Keep *all* communication off
            # the watchdog thread and enforce both elapsed and UTC wall time.
            deadline_wall = time.time() + timeout
            deadline_mono = time.monotonic() + timeout
            done, errors = threading.Event(), []
            def communicate():
                try:
                    process.communicate(input=input_text)
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    done.set()
            communication = threading.Thread(target=communicate, daemon=True)
            communication.start()
            while True:
                remaining = min(deadline_wall - time.time(), deadline_mono - time.monotonic())
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                if done.wait(min(1.0, remaining)):
                    if time.time() > deadline_wall or time.monotonic() > deadline_mono:
                        raise subprocess.TimeoutExpired(command, timeout)
                    if errors:
                        raise errors[0]
                    break
        return process.returncode
    except BaseException:
        # Never enumerate or terminate other sessions by executable/model name.
        if job_assigned:
            owned_job.terminate()
        if process.poll() is None:
            if os.name == "nt" and not job_assigned:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=10, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
            elif os.name != 'nt':
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        if communication is not None:
            communication.join(timeout=10)
        raise
    finally:
        if owned_job is not None:
            owned_job.close()
