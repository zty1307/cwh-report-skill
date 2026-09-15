import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_semantic_repairs import repair_packet, apply_semantic_repairs, complete_decisions
from cwh_semantic_repairs import normalize_excluded_claims


def test_excluded_claims_are_removed_by_disposition_with_original_audit():
    original = [{"items": [{"id": "r1", "decision": "excluded", "claims": [{"claim": "未入选"}]},
                          {"id": "r2", "decision": "eligible", "claims": [{"claim": "入选"}]}]}]
    result = normalize_excluded_claims(original)
    assert result[0]["items"][0]["claims"] == []
    assert result[0]["items"][0]["transport_exclusions"][0]["original_claims"] == [{"claim": "未入选"}]
    assert result[0]["items"][1] == original[0]["items"][1]
    assert original[0]["items"][0]["claims"]


def fixture():
    packets = [{'topic': t, 'items': [{'id': 'r1', 'content': '整篇原文', 'url': 'original'}, {'id': 'r2', 'content': '已排除原文'}]} for t in ('甲', '乙')]
    decisions = [{'topic': t, 'heading': '认为应改进', 'clusters': [], 'items': [
        {'id': 'r1', 'decision': 'eligible', 'reason': '有观点', 'source': '真实媒体', 'published_at': '2026-01-01', 'claims': [{'claim': '旧观点'}]},
        {'id': 'r2', 'decision': 'excluded', 'reason': '事实通稿', 'claims': []}]} for t in ('甲', '乙')]
    return packets, decisions


def test_targeted_repair_keeps_untouched_topics_and_source_identity():
    packets, decisions = fixture()
    request = repair_packet(packets, decisions, ['甲有错误'], lambda p: p)
    assert [p['topic'] for p in request['topics']] == ['甲']
    assert [r['id'] for r in request['topics'][0]['items']] == ['r1']
    patch = {'topics': [{'topic': '甲', 'heading': '建议改进', 'clusters': [], 'items': [
        {'id': 'r1', 'decision': 'eligible', 'reason': '修复范围', 'claims': [{'claim': '新观点'}], 'source': '不可修改媒体', 'published_at': '2000-01-01'}]}]}
    result = apply_semantic_repairs(decisions, request, patch)
    assert result[1] == decisions[1]
    assert result[0]['items'][1] == decisions[0]['items'][1]
    assert result[0]['items'][0]['source'] == '真实媒体'
    assert result[0]['items'][0]['published_at'] == '2026-01-01'
    assert decisions[0]['items'][0]['claims'] == [{'claim': '旧观点'}]


def test_unscoped_error_cannot_hide_unmentioned_topic():
    packets, decisions = fixture()
    request = repair_packet(packets, decisions, ['甲标题有错误', '引文范围错误'], lambda p: p)
    assert len(request['topics']) == 2
    with pytest.raises(ValueError, match='exactly the requested topics'):
        apply_semantic_repairs(decisions, request, {'topics': []})


def test_repair_cannot_add_or_duplicate_a_source():
    packets, decisions = fixture()
    request = repair_packet(packets, decisions, ['甲有错误'], lambda p: p)
    patch = {'topics': [{'topic': '甲', 'items': [{'id': 'r1'}, {'id': 'r1'}]}]}
    with pytest.raises(ValueError, match='exactly the selected source IDs'):
        apply_semantic_repairs(decisions, request, patch)


def test_incomplete_prior_decisions_cannot_use_selected_only_repair():
    packets, decisions = fixture()
    assert complete_decisions(packets, decisions)
    decisions[0]['items'].pop()
    assert not complete_decisions(packets, decisions)
    assert not complete_decisions(packets, [{'topic': '甲'}, {'topic': '甲'}])
