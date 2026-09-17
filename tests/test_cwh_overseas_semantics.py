from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_overseas_semantics import PROMPT, compile_review, media_candidates, social_audit, query_plan, partition_reviewable


def test_partial_foreign_requires_real_search_log_and_preserves_failure_status(tmp_path):
    import json
    import hashlib
    from cwh_semantic_recovery import POLICY, valid_partial_foreign
    from run_cwh_resumable_pipeline import validate_foreign
    registry = json.loads((Path(__file__).resolve().parents[1] / 'config/source_registry.v1.json').read_text('utf-8-sig'))
    queries = query_plan({'topics': [{'topic': '公共服务'}]}, registry)
    for query in queries:
        query.update(status='access_failed', blocker='search deadline exceeded')
    log = tmp_path / 'actual-search.jsonl'
    log.write_text('test timeout log', encoding='utf-8')
    audit = {'attempted': True, 'dry_run': False, 'registry_version': registry['version'],
        'collection_completed': False, 'collection_status': 'partial_completed',
        'command_exit_code': 1, 'collector_exit_code': 1, 'delivery_policy': POLICY,
        'notice': '尚未完成，不代表无报道', 'search_observations': {'queries': queries,
            'host_run': {'session_id': 'timeout-id', 'exit_code': 124, 'log': str(log)},
            'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()}}
    assert valid_partial_foreign(audit)
    target = tmp_path / 'audit.json'
    target.write_text(json.dumps(audit), encoding='utf-8')
    supplements = tmp_path / 'supplements.json'
    supplements.write_text('{"media":[],"comments":[]}', encoding='utf-8')
    assert validate_foreign(target, supplements)
    assert validate_foreign(target, supplements, allow_partial=True) == []
    log.write_text('modified', encoding='utf-8')
    assert not valid_partial_foreign(audit)
    assert validate_foreign(target, supplements, allow_partial=True)


def test_media_candidates_prioritize_registered_overseas_domains():
    observations = {'queries': [{'kind': 'media', 'status': 'completed', 'results': [
        {'title': '国常会报道', 'url': 'https://www.gov.cn/a', 'snippet': '国务院常务会议'},
        {'title': '陆国常会报道', 'url': 'https://www.ctee.com.tw/a', 'snippet': '台湾工商时报 国常会'},
    ]}]}
    registry = {'sources': [{'tier': 'overseas_media', 'domains': ['ctee.com.tw']}]}
    assert [row['url'] for row in media_candidates(observations, registry)] == ['https://www.ctee.com.tw/a']


def test_mainland_meeting_result_without_overseas_signal_is_not_a_candidate():
    observations = {'queries': [{'kind': 'media', 'status': 'completed', 'results': [
        {'title': '国常会报道', 'url': 'https://www.chinanews.com.cn/a', 'snippet': '国务院常务会议'},
    ]}]}
    assert media_candidates(observations, {'sources': []}) == []


def test_overseas_region_domain_is_a_candidate_even_when_unregistered():
    observations = {'queries': [{'kind': 'media', 'status': 'completed', 'results': [
        {'title': '陆国常会报道', 'url': 'https://bank.example.com.tw/a', 'snippet': '国常会城市更新'},
    ]}]}
    assert media_candidates(observations, {'sources': []})[0]['url'] == 'https://bank.example.com.tw/a'


def test_overseas_page_without_meeting_reference_is_prefiltered():
    observations = {'queries': [{'kind': 'media', 'status': 'completed', 'results': [
        {'title': '香港本地五年规划', 'url': 'https://example.hk/a', 'snippet': '香港立法会同日开会'},
    ]}]}
    assert media_candidates(observations, {'sources': []}) == []


def test_compact_overseas_review_requires_readable_body_for_include():
    packet = {'topics': {'1': '城市更新'}, 'rows': [{'id': 1, 'body_status': 'completed'}]}
    result = {'rows': [[1, 'include', '事实性报道', '简体标题', '境外媒体', '忠实摘要', [1], '报道本次会议']]}
    assert compile_review(packet, result)[0]['decision'] == 'include'
    packet['rows'][0]['body_status'] = 'access_failed'
    with pytest.raises(ValueError, match='readable body'):
        compile_review(packet, result)


def test_social_search_zero_and_untraceable_hit_are_distinct():
    zero = {'queries': [{'kind': 'comments', 'status': 'completed', 'query': 'q', 'results': []}]}
    assert social_audit(zero)['status'] == 'no_relevant_result'
    hit = {'queries': [{'kind': 'comments', 'status': 'completed', 'query': 'q', 'results': [
        {'url': 'https://x.com/user/status/1'}]}]}
    assert social_audit(hit)['status'] == 'access_failed'


def test_query_plan_checks_each_required_overseas_source_separately():
    plan = {'monitoring_period': {'start': '2026-05-15'}, 'topics': [{'topic': '城市更新'}]}
    registry = {'sources': [
        {'id': 'ctee', 'name': '台湾工商时报', 'tier': 'overseas_media', 'must_check': True,
         'domains': ['ctee.com.tw']},
        {'id': 'optional', 'name': '可选媒体', 'tier': 'overseas_media', 'must_check': False,
         'domains': ['optional.test']},
    ]}
    tasks = query_plan(plan, registry)
    assert any(row['source_id'] == 'ctee' and '工商時報' in row['query'] and '國常會' in row['query'] for row in tasks)
    assert not any(row.get('source_id') == 'optional' for row in tasks)


def test_hard_eligibility_failures_do_not_consume_semantic_review():
    packet = {'monitoring_period': {'start': '2026-05-15', 'end': '2026-05-18'},
              'topics': {'1': '城市更新'}, 'rows': [
                  {'id': 1, 'body_status': 'access_failed', 'published_at_hint': '2026-05-15'},
                  {'id': 2, 'body_status': 'completed', 'published_at_hint': ''},
                  {'id': 3, 'body_status': 'completed', 'published_at_hint': '2026-05-16'},
              ]}
    reviewable, excluded = partition_reviewable(packet)
    assert [row['id'] for row in reviewable['rows']] == [3]
    assert [row['id'] for row in excluded] == [1, 2]


def test_overseas_prompt_requires_distinct_interpretive_angle_not_agenda_recap():
    assert "只写相对于会议事实新增的影响、机制、风险或评价" in PROMPT
    assert "不复述会议议程" in PROMPT
