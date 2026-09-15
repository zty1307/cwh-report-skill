import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from raw_system_workbook_pipeline import render_workbook_sheets


def test_batch_previews_import_workbook_once_and_check_every_sheet(tmp_path):
    renderer = tmp_path / 'renderer.mjs'
    renderer.touch()
    names = ['关键词', '总事件', '子事件1']

    def render(command, **kwargs):
        assert command[3] == '--batch'
        requests = json.loads(command[4])
        assert [row['sheetName'] for row in requests] == names
        for row in requests:
            Path(row['previewPath']).write_bytes(b'fresh-preview')
        return type('Result', (), {'returncode': 0})()

    with patch('raw_system_workbook_pipeline.subprocess.run', side_effect=render) as run:
        rendered, errors = render_workbook_sheets(tmp_path / 'data.xlsx', names, tmp_path,
                                                 renderer, Path('node'), tmp_path)
    assert run.call_count == 1
    assert rendered == names
    assert errors == []


def test_batch_partial_failure_never_marks_missing_sheet_passed(tmp_path):
    renderer = tmp_path / 'renderer.mjs'
    renderer.touch()

    def render(command, **kwargs):
        first = json.loads(command[4])[0]
        Path(first['previewPath']).write_bytes(b'fresh-preview')
        return type('Result', (), {'returncode': 1})()

    with patch('raw_system_workbook_pipeline.subprocess.run', side_effect=render):
        rendered, errors = render_workbook_sheets(tmp_path / 'data.xlsx', ['A', 'B'], tmp_path,
                                                 renderer, Path('node'), tmp_path)
    assert rendered == ['A']
    assert [row['sheet_name'] for row in errors] == ['B']


def test_empty_batch_starts_no_process(tmp_path):
    renderer = tmp_path / 'renderer.mjs'
    renderer.touch()
    with patch('raw_system_workbook_pipeline.subprocess.run') as run:
        assert render_workbook_sheets(tmp_path / 'data.xlsx', [], tmp_path,
                                     renderer, Path('node'), tmp_path) == ([], [])
    run.assert_not_called()
