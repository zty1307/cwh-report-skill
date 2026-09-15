import json
from pathlib import Path
import sys
from unittest.mock import patch
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_cwh_resumable_pipeline as pipeline


def test_status_reads_existing_job_without_constructing_or_locking_runner(tmp_path, capsys):
    state = {'status': 'running', 'current_stage': 'workbook',
             'stages': [{'stage_id': 'workbook', 'status': 'running'}]}
    state_path = tmp_path / 'pipeline_state.json'
    state_path.write_text(json.dumps(state), encoding='utf-8')
    lock = tmp_path / '.pipeline.lock'
    lock.write_text('owned active worker', encoding='utf-8')
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with patch.object(sys, 'argv', ['pipeline', 'status', '--job-dir', str(tmp_path)]), patch.object(pipeline, 'CwhPipeline') as constructor:
        pipeline.main()
        constructor.assert_not_called()
    assert json.loads(capsys.readouterr().out)['status'] == 'running'
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_status_missing_job_does_not_create_a_workspace(tmp_path):
    missing = tmp_path / 'not-created'
    with patch.object(sys, 'argv', ['pipeline', 'status', '--job-dir', str(missing)]):
        with pytest.raises(FileNotFoundError, match='does not initialize'):
            pipeline.main()
    assert not missing.exists()


def test_status_current_elapsed_is_live_but_completed_time_does_not_keep_growing(tmp_path, capsys):
    state_path = tmp_path / 'pipeline_state.json'
    for status, expected in [('running', 50), ('succeeded', 7)]:
        state_path.write_text(json.dumps({'status': status, 'budget_started_epoch': 1000,
                                        'wall_clock_elapsed_seconds': 7, 'stages': []}), encoding='utf-8')
        frozen = state_path.read_bytes()
        with patch.object(sys, 'argv', ['pipeline', 'status', '--job-dir', str(tmp_path)]), patch.object(pipeline.time, 'time', return_value=1050):
            pipeline.main()
        assert json.loads(capsys.readouterr().out)['wall_clock_elapsed_seconds'] == expected
        assert state_path.read_bytes() == frozen
