"""Lossless batching and provenance checks, not native-model success claims."""
import copy
from pathlib import Path
import sys
import time
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_body_review_batches import partition_review_packet, review_body_batches


def packet(count=17):
    return {'claims': [{'id': f'e{i}', 'source_id': f's{i}', 'topic': '公共服务',
                        'formal_claim': '应保留服务覆盖。', 'excerpt_segments': [{'id': f'e{i}/1', 'text': '完整的对应连续原文。'}]}
                       for i in range(1, count + 1)],
            'sources': [{'id': f's{i}', 'reference_context': '对象确认用开头'} for i in range(1, count + 1)],
            'headings': [{'id': 'h1'}], 'agenda_topics': ['公共服务', '区域发展'],
            'cross_topic_exact_duplicates': [], 'cross_topic_shared_source_spans': []}


def test_parts_cover_every_full_excerpt_once_with_original_ids():
    original = packet()
    frozen = copy.deepcopy(original)
    parts = partition_review_packet(original)
    assert [len(p['claims']) for p in parts] == [8, 8, 1]
    assert [r for p in parts for r in p['claims']] == original['claims']
    assert original == frozen
    for part in parts:
        assert 'headings' not in part
        assert part['agenda_topics'] == original['agenda_topics']
        assert {r['id'] for r in part['sources']} == {r['source_id'] for r in part['claims']}


def test_cross_topic_comparison_stays_together_without_truncating_large_component():
    original = packet()
    group = {'claim_ids': ['e1', 'e17'], 'scope': 'cross-topic'}
    original['cross_topic_shared_source_spans'] = [group]
    parts = partition_review_packet(original)
    together = next(p for p in parts if any(r['id'] == 'e1' for r in p['claims']))
    assert 'e17' in {r['id'] for r in together['claims']}
    assert together['cross_topic_shared_source_spans'] == [group]
    original['cross_topic_exact_duplicates'] = [{'claim_ids': [f'e{i}' for i in range(1, 18)]}]
    assert len(partition_review_packet(original)[0]['claims']) == 17


def test_native_batches_record_actual_runs_and_reject_injected_host_provenance(tmp_path):
    calls = []
    def model(part, prompt, command, folder, name, timeout, **kwargs):
        calls.append(part)
        assert timeout <= 150
        return {'reviews': [{'id': r['id'], 'verdict': 'fully_supported', 'rationale': '当前原文支持。'} for r in part['claims']],
                'review_field_retry': {'original_run': {'session_id': 'fake'}}}, {
                    'session_id': f'actual-{len(calls)}', 'completed_at': 'now'}
    original = packet()
    result, run, origins, audit = review_body_batches(original, 'current evidence only', [], tmp_path,
                                                     time.monotonic() + 300, model)
    assert len(calls) == 3 and len(result['reviews']) == 17
    assert origins['e1']['session_id'] == 'actual-1'
    assert origins['e17']['session_id'] == 'actual-3'
    assert run['session_id'] == 'actual-3'
    assert all(record['review_field_retry'] is None for record in audit)
    assert (tmp_path / 'body_review_batches.json').is_file()


def test_no_budget_does_not_invent_reviews(tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('No model invocation without budget')
    with pytest.raises(TimeoutError, match='budget'):
        review_body_batches(packet(), '', [], tmp_path, time.monotonic() + 10, forbidden)


@pytest.mark.parametrize('change', ['', 'source', 'prompt', 'command', 'result'])
def test_completed_native_review_survives_expired_budget_only_with_matching_hashes(tmp_path, monkeypatch, change):
    import hashlib
    import json
    import cwh_host_research as host
    original = packet(1)
    original['delivery_policy'] = 'deliver_available_with_gaps'
    part = partition_review_packet(original)[0]
    prompt = 'current evidence only'
    suffix = '\n本次只审核本批claims，不审核标题。保持输入短ID，不重新编号；每条从自己的excerpt_segments逐项找依据，不能用另一条摘录替代。'
    command = ['actual-provider']
    digest = hashlib.sha256((prompt + suffix + '\n' + json.dumps(part, ensure_ascii=False, separators=(',', ':'))
                            + '\n' + json.dumps(command)).encode()).hexdigest()
    result = {'reviews': [{'id': 'e1', 'verdict': 'fully_supported', 'rationale': '真实原文支持'}]}
    cache = {'input_sha256': digest, 'result_sha256': hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
             'result': result, 'run': {'session_id': 'earlier-native', 'completed_at': 'earlier-time'}}
    folder = tmp_path / 'body-review-1'
    folder.mkdir()
    if change == 'source':
        original['claims'][0]['excerpt_segments'][0]['text'] = 'changed original source'
    elif change == 'prompt':
        prompt += ' changed'
    elif change == 'command':
        command = ['another-provider']
    elif change == 'result':
        cache['result']['reviews'][0]['rationale'] = 'tampered'
    (folder / 'independent-body-review.cache.json').write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(host, 'invoke', lambda *args, **kwargs: pytest.fail('No new provider call after deadline'))
    actual, _, origins, _ = review_body_batches(original, prompt, command, tmp_path, time.monotonic() - 30, host.semantic_json)
    if not change:
        assert actual == result
        assert origins['e1']['session_id'] == 'earlier-native'
        assert origins['e1']['completed_at'] == 'earlier-time'
    else:
        assert actual['reviews'][0]['verdict'] == 'uncertain'
        assert actual['reviews'][0]['host_unreviewed']


def test_compiler_requires_complete_actual_run_map_and_preserves_it():
    from test_host_compiler import compiled
    from run_cwh_compiled_worker import compile_review
    bundle = compiled()
    raw = {'reviews': [{'id': 'e1', 'verdict': 'fully_supported', 'rationale': '真实审核'}]}
    old, latest = {'session_id': 'first', 'completed_at': 'old-time'}, {'session_id': 'last', 'completed_at': 'new-time'}
    output = compile_review(bundle, raw, latest, 'hash', claim_review_runs={'e1': old})
    assert output['reviews'][0]['reviewer_run_id'] == 'first'
    assert output['reviews'][0]['reviewed_at'] == 'old-time'
    assert output['reviewer_run_ids'] == ['last', 'first']
    with pytest.raises(ValueError, match='cover'):
        compile_review(bundle, raw, latest, 'hash', claim_review_runs={})


def test_timeout_in_first_batch_does_not_discard_later_real_review(tmp_path):
    from cwh_host_research import HostModelError
    original = packet(9)
    original['delivery_policy'] = 'deliver_available_with_gaps'
    calls = []
    def model(part, *args, **kwargs):
        calls.append(part)
        if len(calls) == 1:
            raise HostModelError('timeout', 124, run={'session_id': 'failed', 'exit_code': 124})
        return {'reviews': [{'id': r['id'], 'verdict': 'fully_supported', 'rationale': '真实原文支持'} for r in part['claims']]}, {
            'session_id': 'actual-second', 'completed_at': 'now'}
    result, run, origins, records = review_body_batches(original, '', [], tmp_path, time.monotonic() + 400, model)
    assert len(calls) == 2 and result['reviews'][-1]['verdict'] == 'fully_supported'
    assert all(r['verdict'] == 'uncertain' and r['host_unreviewed']['actual_run']['session_id'] == 'failed'
               for r in result['reviews'][:-1])
    assert origins['e1']['model_invoked'] is False
    assert origins['e9']['session_id'] == 'actual-second'


def test_uncertainty_is_never_attributed_to_native_model_and_is_removed_from_prose(tmp_path):
    from test_host_compiler import compiled
    from run_cwh_compiled_worker import independent_packet, compile_review
    from cwh_review_retention import retain_reviewed_content, retention_packet, validate_retention
    from domestic_evidence_mapping import apply_semantic_review_packet
    bundle = compiled()
    bundle['metadata']['delivery_policy'] = 'deliver_available_with_gaps'
    request = independent_packet(bundle)
    def forbidden(*args, **kwargs):
        pytest.fail('Expired budget must not call provider')
    result, run, origins, _ = review_body_batches(request, '', [], tmp_path, time.monotonic(), forbidden)
    initial = compile_review(bundle, result, run, 'original-hash', claim_review_runs=origins)
    assert initial['reviews'][0]['reviewed_by'].startswith('host_unreviewed:')
    repaired, actions = retain_reviewed_content(bundle, initial)
    assert not any(c['evidence'] for t in repaired['viewpoints']['by_topic'] for c in t['clusters'])
    combined = retention_packet(repaired, initial, actions, run, 'repaired-hash')
    validate_retention(bundle, repaired, initial, combined)
    _, errors = apply_semantic_review_packet(repaired, combined, source_bundle_sha256='repaired-hash')
    assert errors == []
    assert repaired['metadata']['research_budget_gaps']
