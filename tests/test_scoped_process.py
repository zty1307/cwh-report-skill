import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cwh_scoped_process import run_scoped_command
from cwh_pipeline_runtime import PipelineRunner, StageSpec


def test_timeout_stops_owned_child_before_it_writes(tmp_path):
    marker = tmp_path / "orphan.txt"
    child = f"import time; from pathlib import Path; time.sleep(1); Path({str(marker)!r}).write_text('orphan')"
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(10)"
    with pytest.raises(subprocess.TimeoutExpired):
        run_scoped_command([sys.executable, "-c", parent], cwd=tmp_path, timeout=0.3)
    time.sleep(1.1)
    assert not marker.exists()


def test_large_stdin_is_timed_even_when_child_never_reads_it(tmp_path):
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_scoped_command([sys.executable, '-c', 'import time; time.sleep(30)'], cwd=tmp_path,
                           input_text='x' * 2_000_000, timeout=0.3)
    assert time.monotonic() - started < 5


def test_timeout_does_not_stop_an_unrelated_process(tmp_path):
    import os
    sibling = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            run_scoped_command([sys.executable, '-c', 'import time; time.sleep(30)'], cwd=tmp_path, timeout=.2)
        assert sibling.poll() is None
    finally:
        sibling.terminate()
        sibling.wait(timeout=5)


def test_forward_wall_clock_jump_does_not_grant_extra_runtime(tmp_path, monkeypatch):
    ticks = iter([100.0, 100.0, 1000.0, 1000.0])
    monkeypatch.setattr('cwh_scoped_process.time.time', lambda: next(ticks, 1000.0))
    with pytest.raises(subprocess.TimeoutExpired):
        run_scoped_command([sys.executable, '-c', 'import time; time.sleep(30)'], cwd=tmp_path, timeout=0.2)


def test_research_deadline_preserves_delivery_time(tmp_path, monkeypatch):
    runner = PipelineRunner(tmp_path, [StageSpec("research", "Research"), StageSpec("render", "Render")],
                            {"research": lambda *_: None, "render": lambda *_: None},
                            pipeline_name="deadline", input_contract={"wall_clock_budget_seconds": 3600,
                                                                      "research_deadline_seconds": 2700})
    runner.state["budget_started_epoch"] = 1000
    monkeypatch.setattr("cwh_pipeline_runtime.time.time", lambda: 3699)
    assert runner.remaining_budget_seconds("research") == 1
    assert runner.remaining_budget_seconds("render") == 901
