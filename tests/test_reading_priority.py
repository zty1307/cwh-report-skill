import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_reading_priority import prioritize_pages
from cwh_host_research import HostModelError


def observations():
    return {'queries': [{'results': [
        {'url': 'https://example.test/a', 'title': '会议通稿', 'snippet': '发现摘要甲'},
        {'url': 'https://example.test/b', 'title': '政策深度采访', 'snippet': '发现摘要乙'}]}]}


def test_native_ranking_uses_only_observed_urls_and_reuses_actual_run(tmp_path):
    observed = observations()
    before = copy.deepcopy(observed)
    calls = []
    def model(packet, *args, **kwargs):
        calls.append(packet)
        return {'items': [{'id': 'u2'}]}, {'session_id': 'actual-native-run'}
    args = (observed, '公共服务', 1, ['https://example.test/a'], [], tmp_path, 30, model)
    assert prioritize_pages(*args) == ['https://example.test/b']
    assert prioritize_pages(*args) == ['https://example.test/b']
    assert len(calls) == 1 and observed == before
    payload = json.loads((tmp_path / 'reading_priority.json').read_text('utf-8'))['payload']
    assert payload['actual_run']['session_id'] == 'actual-native-run'
    assert 'not_semantic_approval' in payload['method']


@pytest.mark.parametrize('failure', ['unknown_id', 'timeout'])
def test_optional_ranking_failure_does_not_invent_or_certify_evidence(tmp_path, failure):
    def model(*args, **kwargs):
        if failure == 'timeout':
            raise HostModelError('actual timeout', 124, run={'session_id': 'actual-timeout'})
        return {'items': [{'id': 'invented'}]}, {'session_id': 'actual-invalid'}
    assert prioritize_pages(observations(), '公共服务', 1, ['https://example.test/a'], [],
                            tmp_path, 30, model) == ['https://example.test/a']
    payload = json.loads((tmp_path / 'reading_priority.json').read_text('utf-8'))['payload']
    assert payload['method'] == 'deterministic_discovery_order' and payload['error']


def test_permission_failure_is_not_relabelled_as_optional_missing_evidence(tmp_path):
    def denied(*args, **kwargs):
        raise HostModelError('permission', 23)
    with pytest.raises(HostModelError):
        prioritize_pages(observations(), '公共服务', 1, ['https://example.test/a'], [], tmp_path, 30, denied)


def test_priority_shape_is_accepted_by_production_response_decoder():
    from run_cwh_inline_review import response_object
    assert response_object('{"items":[{"id":"u2"}]}') == {'items': [{'id': 'u2'}]}
