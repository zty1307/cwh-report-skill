import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_semantic_repairs import repair_missing_author_items


def test_completion_preserves_existing_native_items_and_headings(monkeypatch, tmp_path):
    packet = {'topic': '政策甲', 'items': [{'id': 'r1', 'segments': [{'id': 'r1/1', 'text': '原文一'}]},
        {'id': 'w19', 'segments': [{'id': 'w19/1', 'text': '完整原文十九'}]}]}
    decision = {'heading': '原生标题', 'clusters': [{'key': 'k1', 'heading': '原生簇'}],
        'items': [{'id': 'r1', 'decision': 'eligible', 'reason': '原生理由', 'claims': [{'claim': '原生观点'}]}]}
    original = copy.deepcopy(decision)
    def model(request, prompt, command, workspace, label, timeout, **kwargs):
        assert request['items'] == [packet['items'][1]]
        assert request['existing_clusters'] == decision['clusters']
        assert timeout <= 45
        return {'items': [{'id': 'w19', 'decision': 'excluded', 'reason': '仅政策一手事实', 'claims': []}]}, {'session_id': 'native'}
    monkeypatch.setattr('cwh_host_research.semantic_json', model)
    result, run = repair_missing_author_items(packet, decision, '原审核规则', [], tmp_path, 90, 'coverage')
    assert decision == original
    assert result['items'][0] == original['items'][0]
    assert result['heading'] == original['heading'] and result['clusters'] == original['clusters']
    assert result['transport_repairs'][0]['original_items'] == original['items']
    assert run['session_id'] == 'native'


@pytest.mark.parametrize('rows', [
    [{'id': 'r1'}, {'id': 'r1'}], [{'id': 'unknown'}], [{'id': None}], [None]])
def test_invalid_existing_identity_is_not_repaired(monkeypatch, tmp_path, rows):
    monkeypatch.setattr('cwh_host_research.semantic_json', lambda *a, **k: pytest.fail('No semantic call'))
    with pytest.raises(ValueError):
        repair_missing_author_items({'items': [{'id': 'r1'}]}, {'items': rows}, '', [], tmp_path, 90, 'coverage')


@pytest.mark.parametrize('patches', [
    [{'id': 'r1', 'decision': 'excluded', 'reason': '错ID'}],
    [{'id': 'r2', 'decision': 'excluded', 'reason': ''}],
    [{'id': 'r2', 'decision': 'excluded', 'reason': '重复'}] * 2, []])
def test_invalid_completion_does_not_change_original(monkeypatch, tmp_path, patches):
    original = {'items': [{'id': 'r1', 'decision': 'excluded', 'reason': '原生理由', 'claims': []}]}
    before = copy.deepcopy(original)
    monkeypatch.setattr('cwh_host_research.semantic_json', lambda *a, **k: ({'items': patches}, {'session_id': 'native'}))
    with pytest.raises(ValueError, match='exactly missing IDs'):
        repair_missing_author_items({'topic': '政策甲', 'items': [{'id': 'r1'}, {'id': 'r2'}]}, original,
            '', [], tmp_path, 90, 'coverage')
    assert original == before


def test_no_call_if_complete_or_no_budget(monkeypatch, tmp_path):
    monkeypatch.setattr('cwh_host_research.semantic_json', lambda *a, **k: pytest.fail('No semantic call'))
    decision = {'items': [{'id': 'r1'}]}
    assert repair_missing_author_items({'items': [{'id': 'r1'}]}, decision, '', [], tmp_path, 90, 'coverage') == (decision, None)
    with pytest.raises(ValueError, match='missing IDs'):
        repair_missing_author_items({'items': [{'id': 'r1'}, {'id': 'r2'}]}, decision, '', [], tmp_path, 14, 'coverage')
