import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cwh_remaining_research import operation_workspace


def test_short_workspace_fits_native_log_and_keeps_full_identity(tmp_path):
    key='a'*64
    path=operation_workspace(tmp_path,key)
    assert path.name==key[:16] and len(path.name)==16
    log=path/'author-topic-1.0ea202d4-6a93-4c0d-94e5-0846496030c1.jsonl'
    log.write_text('native log path probe',encoding='utf-8')
    assert operation_workspace(tmp_path,key)==path
    with pytest.raises(ValueError):operation_workspace(tmp_path,key[:16]+'b'*48)


def test_real_regression_run_prefix_stays_under_windows_limit(tmp_path):
    base=Path('D:/Codex/Projects/CWH/outputs/cwh1022_auto45_v1/runs/full-glm-5.3-ioa-20261022-143131-894faac4/job')
    log=base/'worker/domestic_remaining_research/readings'/('a'*16)/'author-topic-1.0ea202d4-6a93-4c0d-94e5-0846496030c1.jsonl'
    assert len(str(log))<240
    review=base/'rr/worker/domestic_evidence_verification/b1'/'retained-heading-review.0ea202d4-6a93-4c0d-94e5-0846496030c1.run.json'
    assert len(str(review))<250
