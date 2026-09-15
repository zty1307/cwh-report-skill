import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_cwh_inline_review import configured_raw_review_batch_size


def test_default_and_local_small_batches(monkeypatch):
    monkeypatch.delenv('CWH_RAW_REVIEW_BATCH_SIZE', raising=False)
    assert configured_raw_review_batch_size() == 12
    monkeypatch.setenv('CWH_RAW_REVIEW_BATCH_SIZE', '3')
    assert configured_raw_review_batch_size() == 3


@pytest.mark.parametrize('value', ['0', '13', '-1', '3.0', 'x', '', ' 3'])
def test_invalid_batch_sizes_rejected_before_native_calls(monkeypatch, value):
    monkeypatch.setenv('CWH_RAW_REVIEW_BATCH_SIZE', value)
    with pytest.raises(ValueError, match='1 to 12'):
        configured_raw_review_batch_size()
