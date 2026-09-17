"""A timed-out source remains unread; no fabricated semantic rejection."""
import copy
from pathlib import Path
import sys
import time
from unittest.mock import patch
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_host_compiler import fixture
from cwh_semantic_compiler import compile_topic
from cwh_host_research import HostModelError
from run_cwh_compiled_worker import review_author_article_batches


def test_actual_timeout_is_deferred_not_counted_as_semantic_raw_review():
    packet, decision, observation, plan = fixture()
    packet['delivery_policy'] = 'deliver_available_with_gaps'
    decision['items'][0].update(decision='excluded', claims=[], reason='原文保留，未完成阅读')
    failure = {'id': 'r1', 'reason': 'actual timeout', 'actual_run': {'session_id': 'failed-native', 'exit_code': 124}}
    compiled = compile_topic(packet, decision, observation, plan, 'bounded_60m', 'v1', 'author', reading_deferrals=[failure])
    audit = compiled['research_audit']['domestic_media_research']
    review = audit['public_article_corpus_review']['topic_reviews'][0]
    assert review['reviewed_record_ids'] == [] and review['excluded'] == []
    row = audit['candidate_pool_by_topic'][0]['candidates'][0]
    assert row['source_snapshot']['source_text'] == packet['items'][0]['content']
    assert row['review_scope'] == 'full_text_available_semantic_review_deferred'
    assert row['machine_disposition']['actual_run']['session_id'] == 'failed-native'
    from prepare_cwh_corpus_index import complete_corpus_deferrals
    corpus = {'candidates': [{'record_id': 'raw-1', 'topic_hits': [1]}, {'record_id': 'never-read', 'topic_hits': [1]}]}
    final = complete_corpus_deferrals(compiled, corpus, [packet['topic']])
    assert final['research_audit']['domestic_media_research']['public_article_corpus_review']['topic_reviews'][0]['deferred_record_ids'] == ['never-read', 'raw-1']


def test_deferral_cannot_certify_eligible_claim_or_be_forged_without_actual_timeout():
    packet, decision, observation, plan = fixture()
    packet['delivery_policy'] = 'deliver_available_with_gaps'
    params = packet, decision, observation, plan, 'bounded_60m', 'v1', 'author'
    with pytest.raises(ValueError, match='actual timeout'):
        compile_topic(*params, reading_deferrals=[{'id': 'r1', 'actual_run': {'exit_code': 0}}])
    with pytest.raises(ValueError, match='cannot supply'):
        compile_topic(*params, reading_deferrals=[{'id': 'r1', 'actual_run': {'exit_code': 124}}])


def test_available_batch_timeout_keeps_finished_other_reading_and_does_not_retry(tmp_path):
    packet, _, _, _ = fixture()
    packet['items'] = packet['items'][:1]
    second = copy.deepcopy(packet['items'][0])
    second['id'] = 'r2'
    packet['items'].append(second)
    packet['delivery_policy'] = 'deliver_available_with_gaps'
    groups = [{'items': [packet['items'][0]]}, {'items': [packet['items'][1]]}]
    fail = HostModelError('actual timeout', 124, run={'session_id': 'timeout-1', 'exit_code': 124})
    done = ([{'items': [{'id': 'r2', 'decision': 'excluded', 'reason': '读完只有部署，无独立判断', 'claims': []}]}],
            {'session_id': 'completed-2', 'model_invoked': True})
    with patch('run_cwh_compiled_worker.author_topic_decisions', side_effect=[fail, done]) as native:
        result, run = review_author_article_batches(packet, groups, '', [], tmp_path,
            time.monotonic() + 120, reuse_cache=False, feedback=[], maximum_request_seconds=90)
    assert native.call_count == 2
    assert len(result['items']) == 2
    assert run['article_reading_deferrals'][0]['id'] == 'r1'
    assert run['batch_runs'] == [done[1]]
    assert run['synthesis_run']['model_invoked'] is False


@pytest.mark.parametrize('code,policy', [(23, 'deliver_available_with_gaps'), (124, '')])
def test_permission_error_and_strict_timeout_still_stop(code, policy, tmp_path):
    packet, _, _, _ = fixture()
    packet['items'] = packet['items'][:1]
    packet['delivery_policy'] = policy
    with patch('run_cwh_compiled_worker.author_topic_decisions', side_effect=HostModelError('actual failure', code)), pytest.raises(HostModelError):
        review_author_article_batches(packet, [{'items': packet['items']}], '', [], tmp_path,
            time.monotonic() + 120, reuse_cache=False, feedback=[], maximum_request_seconds=90)


def test_expired_batch_budget_preserves_every_full_source_as_unread(tmp_path):
    packet, _, _, _ = fixture()
    packet['delivery_policy'] = 'deliver_available_with_gaps'
    frozen = copy.deepcopy(packet)
    groups = [{'items': [row]} for row in packet['items']]
    with patch('run_cwh_compiled_worker.author_topic_decisions') as native:
        result, run = review_author_article_batches(packet, groups, '', [], tmp_path,
            time.monotonic() - 1, reuse_cache=False, feedback=[], maximum_request_seconds=180)
    native.assert_not_called()
    assert packet == frozen
    assert len(run['article_reading_deferrals']) == len(packet['items'])
    assert all(d['kind'] == 'budget_exhausted_before_call' for d in run['article_reading_deferrals'])
    assert all(not item['claims'] for item in result['items'])


def test_synthesis_timeout_keeps_actual_extraction_without_host_written_judgments(tmp_path):
    packet, decision, observation, plan = fixture()
    packet['delivery_policy'] = 'deliver_available_with_gaps'
    frozen = copy.deepcopy(decision['items'])
    done = ([{'items': decision['items']}], {'session_id': 'actual-reader', 'seconds': 1})
    failure = HostModelError('synthesis timeout', 124, run={'session_id': 'timed-out-grouping', 'exit_code': 124})
    with patch('run_cwh_compiled_worker.author_topic_decisions', return_value=done), patch(
            'run_cwh_compiled_worker.native_topic_synthesis', side_effect=failure):
        result, run = review_author_article_batches(packet, [{'items': packet['items']}], '', [], tmp_path,
            time.monotonic() + 300, reuse_cache=False, feedback=[], maximum_request_seconds=180)
    assert result['heading'] == packet['topic']
    for old, new in zip(frozen, result['items']):
        for first, second in zip(old.get('claims', []), new.get('claims', [])):
            assert {k: v for k, v in first.items() if k != 'cluster'} == {k: v for k, v in second.items() if k != 'cluster'}
    assert run['synthesis_run']['model_invoked'] is False
    compiled = compile_topic(packet, result, observation, plan, 'bounded_60m', 'v1', 'reader')
    assert compiled['viewpoints']['by_topic'][0]['clusters'][0]['evidence']
