"""Regression: raw nominations must not starve independent public-web reading."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_host_compiler import fixture
import run_cwh_compiled_worker as worker
from cwh_web_research_budget import is_index_url, synthesis_reserve


def test_existing_raw_claim_still_allows_web_reading_in_100_second_slice(tmp_path, monkeypatch):
    packet, decision, _, _ = fixture()
    raw = packet['items'][0]
    web = {**copy.deepcopy(raw), 'id': 'w1', 'origin': 'web'}
    packet.update(items=[raw, web], delivery_policy='deliver_available_with_gaps',
                  screen_integration_active=True,
                  screened_readings=[copy.deepcopy(decision['items'][0])])
    clock = [1000.0]
    monkeypatch.setattr(worker.time, 'monotonic', lambda: clock[0])
    calls = []
    def read(packets, prompt, command, folder, deadline, **kwargs):
        calls.append([item['id'] for item in packets[0]['items']])
        assert deadline - clock[0] == 75
        clock[0] += 35
        return [{'items': [{'id': 'w1', 'decision': 'excluded', 'claims': [],
                            'reason': 'actual native web reading'}]}], {'session_id': 'web-reading'}
    def synth(request, choices, command, folder, timeout, model_call, **kwargs):
        assert timeout == 65
        return {'items': choices}, {'session_id': 'separate-synthesis'}
    monkeypatch.setattr(worker, 'author_topic_decisions', read)
    monkeypatch.setattr(worker, 'native_topic_synthesis', synth)
    _, run = worker.review_author_article_batches(packet, [{'items': [web]}], '', [],
        tmp_path, 1100, reuse_cache=False, feedback=[], maximum_request_seconds=180)
    assert calls == [['w1']]
    assert run['article_reading_deferrals'] == []
    assert run['batch_runs'][0]['session_id'] == 'web-reading'


def test_index_urls_are_delayed_without_deleting_discovery():
    observations = {'queries': [{'results': [
        {'url': 'https://example.test/?tracking=abc', 'title': '门户首页'},
        {'url': 'https://example.test/news/123.html', 'title': '政策分析'}]}]}
    original = copy.deepcopy(observations)
    assert worker.balanced_fetch_urls(observations, 1) == ['https://example.test/news/123.html']
    assert set(worker.balanced_fetch_urls(observations, 2)) == {
        'https://example.test/?tracking=abc', 'https://example.test/news/123.html'}
    assert observations == original
    assert not is_index_url('https://example.test/index.html?item_id=123')


def test_reserve_stays_inside_original_deadline_and_legacy_policy():
    assert synthesis_reserve(100, integrated=True, has_claims=True) == 25
    assert synthesis_reserve(100, integrated=False, has_claims=True) == 100
    assert synthesis_reserve(10, integrated=True, has_claims=True) == 10
    assert synthesis_reserve(100, integrated=True, has_claims=False) == 0


def test_final_web_use_counts_actual_body_ids_not_author_selected_labels():
    from cwh_web_research_audit import summarize
    bundle = {'viewpoints': {'by_topic': [{'topic': 'A', 'clusters': [
        {'evidence': [{'candidate_id': 'retained'}]}]}]},
        'research_audit': {'domestic_media_research': {'candidate_pool_by_topic': [{
            'topic': 'A', 'candidates': [
                {'candidate_id': 'retained', 'discovery_origin': 'open_web',
                 'decision': 'eligible',
                 'url': 'https://example.test/a', 'review_scope': 'full_text_semantic_review',
                 'formal_claim': 'supported'},
                {'candidate_id': 'rejected', 'discovery_origin': 'open_web',
                 'decision': 'eligible',
                 'url': 'https://example.test/a', 'review_scope': 'full_text_semantic_review',
                 'formal_use': 'selected', 'formal_claim': 'not retained'}]}]}}}
    result = summarize(bundle)['totals']
    assert result['web_native_read_urls'] == 1
    assert result['web_nominated_claims'] == 2
    assert result['web_final_body_claims'] == 1


def test_query_counter_does_not_count_raw_fulltext_review_as_web_search():
    from cwh_web_research_audit import summarize
    bundle={'viewpoints':{'by_topic':[]},'research_audit':{'domestic_media_research':{
        'candidate_pool_by_topic':[{'topic':'A','candidates':[],'saturation':{'rounds':[{'executions':[
            {'route':'monitoring_corpus','status':'completed'},
            {'route':'open_web','status':'completed'},
            {'route':'public_platform','status':'access_failed'}]}]}}]}}}
    assert summarize(bundle)['topics'][0]['completed_search_queries']==1
