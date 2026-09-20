import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from publish_cwh_artifacts import publish


def test_names_use_actual_generation_time_and_preserve_bytes(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    (source / 'report_data.json').write_text(json.dumps({'generated_at': '2026-09-19T17:12:30+00:00'}))
    for name in ('cwh_formal_report.docx', 'cwh_dashboard.html', 'cwh_data_workbook.xlsx'):
        (source / name).write_bytes(b'unchanged-test-fixture')
    result = publish(source, tmp_path / 'output', 'Example-model')
    assert Path(result['files'][0]['output']).name == 'Example-model_0112_报告.docx'
    assert all(Path(r['output']).read_bytes() == Path(r['source']).read_bytes() for r in result['files'])
    with pytest.raises(FileExistsError):
        publish(source, tmp_path / 'output', 'Example-model')
