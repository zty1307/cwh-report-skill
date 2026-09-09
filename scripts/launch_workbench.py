"""Start/reuse the loopback workbench without a terminal or automatic shutdown."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser


def get_json(url: str, timeout: int = 5) -> dict:
    with urlopen(url, timeout=timeout) as response:
        return json.load(response)


def launch(dashboard: Path, library_root: Path, port: int, open_browser: bool) -> dict:
    dashboard = dashboard.resolve(strict=True)
    library_root = library_root.resolve(strict=True)
    base = f"http://127.0.0.1:{port}"
    with socket.socket() as probe:
        occupied = probe.connect_ex(("127.0.0.1", port)) == 0
    process = None
    if occupied:
        manifest = get_json(base + "/api/manifest")
        if manifest.get("application") != "cwh-report-workbench" or not manifest.get("features", {}).get("resumable_pipeline"):
            raise RuntimeError(f"Port {port} belongs to another service. No process was stopped.")
    else:
        log_dir = dashboard.parent / "runtime"
        log_dir.mkdir(exist_ok=True)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        dependencies = library_root.parent / ".runtime-deps"
        if dependencies.is_dir():
            env["PYTHONPATH"] = str(dependencies) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        command = [sys.executable, str(Path(__file__).with_name("serve_dashboard.py")), str(dashboard),
                   "--library-root", str(library_root), "--workspace", str(library_root.parent),
                   "--host", "127.0.0.1", "--port", str(port), "--report-runner", "pipeline", "--no-open"]
        flags = (subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS) if os.name == "nt" else 0
        with (log_dir / "workbench.log").open("ab") as log:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       cwd=str(library_root.parent), env=env, creationflags=flags,
                                       start_new_session=os.name != "nt")
        deadline = time.monotonic() + 30
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"Workbench exited. See {log_dir / 'workbench.log'}")
            try:
                get_json(base + "/api/manifest")
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
    # One bounded archive request, not repeated short requests on a cold scan.
    archive = get_json(base + "/api/archive", timeout=60)
    with urlopen(base + "/cwh_dashboard.html", timeout=10) as response:
        if response.status != 200:
            raise RuntimeError("Dashboard is not available")
    result = {"status": "ok", "url": base + "/cwh_dashboard.html", "reused": occupied,
              "pid": process.pid if process else None, "archive_counts": archive.get("counts", {})}
    if open_browser:
        webbrowser.open(result["url"])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dashboard", type=Path)
    parser.add_argument("--library-root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    print(json.dumps(launch(args.dashboard, args.library_root, args.port, not args.no_open), ensure_ascii=False))


if __name__ == "__main__":
    main()
