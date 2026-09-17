import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_search_budget import query_budget_evidence, valid_query_budget_stop
from cwh_available_delivery import prepare_available_delivery
from run_cwh_resumable_pipeline import validate_analysis_bundle


def material():
    rows = [{'query_id': f'q{i}', 'query': f'当前议题公开解读具体查询{i}',
             'route': 'public_platform' if i == 9 else 'open_web',
             'backend': 'test_search', 'executed_at': '2026-09-17T10:00:00+08:00',
             'status': 'completed', 'result_urls': [], 'result_count': 0,
             'retained_candidate_ids': []} for i in range(10)]
    saturation = {'completed': True,
                  'stop_reason': 'coverage_minimum_then_one_zero_new_round_or_budget_exhausted',
                  'rounds': [{'round': 1, 'new_independent_viewpoints': 1, 'executions': rows}]}
    return {'research_audit': {'domestic_media_research': {'execution_profile': 'bounded_60m',
            'candidate_pool_by_topic': [{'topic': '动态议题', 'candidates': [], 'saturation': saturation}]}},
            'viewpoints': {'by_topic': []}}


def test_budget_stop_does_not_falsify_zero_new_round_or_certify_saturation():
    original = material()
    before = copy.deepcopy(original)
    result = prepare_available_delivery(original)
    saturation = result['research_audit']['domestic_media_research']['candidate_pool_by_topic'][0]['saturation']
    assert saturation['completed'] is False
    assert saturation['rounds'][0]['new_independent_viewpoints'] == 1
    assert valid_query_budget_stop(saturation, 'bounded_60m')
    assert saturation['budget_stop']['saturation_proven'] is False
    assert result['metadata']['research_budget_gaps']
    assert original == before
    assert prepare_available_delivery(result) == result


@pytest.mark.parametrize('change', ['short', 'duplicate_id', 'duplicate_query', 'not_executed', 'waiting_login', 'missing_urls'])
def test_missing_or_duplicate_executions_cannot_claim_budget_exhaustion(change):
    saturation = material()['research_audit']['domestic_media_research']['candidate_pool_by_topic'][0]['saturation']
    rows = saturation['rounds'][0]['executions']
    if change == 'short':
        rows.pop()
    elif change == 'duplicate_id':
        rows[-1]['query_id'] = rows[0]['query_id']
    elif change == 'duplicate_query':
        rows[-1]['query'] = rows[0]['query']
    elif change == 'not_executed':
        rows[-1]['executed_at'] = ''
    elif change == 'waiting_login':
        rows[-1]['status'] = 'waiting_login'
    else:
        rows[-1].pop('result_urls')
    assert query_budget_evidence(saturation, 'bounded_60m') is None


def test_exhaustive_and_forged_cap_cannot_use_budget_stop():
    result = prepare_available_delivery(material())
    saturation = result['research_audit']['domestic_media_research']['candidate_pool_by_topic'][0]['saturation']
    assert not valid_query_budget_stop(saturation, 'exhaustive')
    saturation['budget_stop']['configured_max_queries'] = 1
    assert not valid_query_budget_stop(saturation, 'bounded_60m')


def test_validator_allows_only_bounded_available_budget_stop_and_keeps_other_gates(tmp_path):
    result = prepare_available_delivery(material())
    path = tmp_path / 'analysis.json'
    path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    issues = validate_analysis_bundle(path, ['动态议题'], allow_deferred_corpus=True)
    assert issues  # Missing viewpoints, source coverage etc. are still errors.
    assert not any('轮无新增' in x or '尚未完成候选池饱和' in x for x in issues)
    strict = validate_analysis_bundle(path, ['动态议题'], allow_deferred_corpus=False)
    assert any('轮无新增' in x for x in strict)
    result['metadata']['delivery_policy'] = 'strict'
    path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    assert any('轮无新增' in x for x in validate_analysis_bundle(path, ['动态议题'], allow_deferred_corpus=True))


def test_budget_gap_makes_rendered_audit_not_formally_ready():
    from cwh_orchestrator import build_system_audit
    metadata = prepare_available_delivery(material())['metadata']
    audit = build_system_audit({}, [], [], {'by_topic': []}, metadata)
    assert metadata['research_budget_gaps'][0] in audit['data_gaps']
    assert metadata['research_budget_gaps'][0] in audit['acceptance']['blockers']
    assert audit['acceptance']['ready_for_formal_delivery'] is False
