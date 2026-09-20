import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_evidence_window_transport import hotword_nomination_transport, pool_hotword_windows
from test_hotword_batches import packet


def test_nomination_removes_only_old_candidate_bookkeeping_and_retains_all_original_text():
    source = packet()
    source['existing_reviewed_terms'] = ['公共服务']
    original = copy.deepcopy(source)
    pooled = pool_hotword_windows(source)
    nomination = hotword_nomination_transport(source)
    assert source == original
    assert nomination['source_window_pool'] == pooled['source_window_pool']
    assert nomination['source_urls'] == pooled['source_urls']
    for key in pooled.keys() - {'candidates', 'candidate_count', 'candidate_source_windows', 'transport_note'}:
        assert nomination[key] == pooled[key]
    assert not {'candidates', 'candidate_count', 'candidate_source_windows'} & nomination.keys()
