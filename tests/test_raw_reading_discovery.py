"""Discovery is only reading order; mocked calls are not quality certificates."""
import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_raw_reading_discovery import discovery_cards, prioritize_raw_articles
from cwh_host_research import HostModelError


def articles():
    return [{'record_id': 'original', 'title': '会议通稿', 'content': '会议部署公共服务有关工作。', 'source': '来源甲'},
            {'record_id': 'extra', 'title': '政策如何影响家庭选择', 'content': '公共服务资源需要衔接实际需求。\n建议延长服务时间，因为家长下班较晚。', 'source': '来源乙'}]


def test_extra_lanes_keep_old_candidates_and_exact_unreviewed_hints():
    rows = articles()
    frozen = copy.deepcopy(rows)
    cards = discovery_cards(rows, rows[:1], ['公共服务'])
    assert [r['record_id'] for r in cards] == ['original', 'extra']
    assert rows == frozen
    for card in cards:
        source = next(r for r in rows if r['record_id'] == card['record_id'])
        assert all(hint in source['content'] for hint in card['unreviewed_excerpt_hints'])
        assert 'reviewed' not in card and 'decision' not in card


def index():
    cards = discovery_cards(articles(), articles()[:1], ['公共服务'])
    for card in cards:
        card['full_text_path'] = '/original/' + card['record_id'] + '.json'
    return {'topic': '公共服务', 'shortlist': cards[:1], 'discovery_shortlist': cards}


def test_exact_named_analysis_is_visible_beyond_generic_opening_hint():
    row = {'record_id': 'named', 'title': '政策观察', 'content':
           '公共服务政策发布。\n预计未来需要资源，因为需求变化。\n研究员张明认为，公共服务开放时间需要衔接居民工作安排。'}
    card = discovery_cards([row], [row], ['公共服务'])[0]
    assert card['professional_attribution_hint_count'] > 0
    assert any('张明认为' in hint for hint in card['unreviewed_excerpt_hints'])
    assert all(hint in row['content'] for hint in card['unreviewed_excerpt_hints'])


def test_native_can_select_beyond_prior_shortlist_without_source_rewriting(tmp_path):
    indexed = index()
    frozen = copy.deepcopy(indexed)
    calls = []
    def native(request, *args, **kwargs):
        calls.append(request)
        assert 'full_text_path' not in str(request)
        return {'items': [{'id': 'r2'}]}, {'session_id': 'native-discovery'}
    args = indexed, 1, [], tmp_path, 30, native
    assert prioritize_raw_articles(*args) == [indexed['discovery_shortlist'][1]]
    assert prioritize_raw_articles(*args) == [indexed['discovery_shortlist'][1]]
    assert len(calls) == 1 and indexed == frozen
    audit = json.loads((tmp_path / 'raw_reading_priority.json').read_text('utf-8'))['payload']
    assert audit['actual_run']['session_id'] == 'native-discovery'
    assert 'not_evidence_approval' in audit['method']


@pytest.mark.parametrize('failure', ['timeout', 'unknown', 'duplicate'])
def test_optional_discovery_failure_keeps_original_reading_order(tmp_path, failure):
    indexed = index()
    def native(*args, **kwargs):
        if failure == 'timeout':
            raise HostModelError('actual timeout', 124, run={'session_id': 'native-timeout'})
        return {'items': [{'id': 'r999'}] if failure == 'unknown' else [{'id': 'r2'}, {'id': 'r2'}]}, {'session_id': 'native-invalid'}
    assert prioritize_raw_articles(indexed, 1, [], tmp_path, 30, native) == indexed['shortlist']
    assert json.loads((tmp_path / 'raw_reading_priority.json').read_text('utf-8'))['payload']['error']


def test_permission_errors_are_not_treated_as_optional_timeouts(tmp_path):
    def denied(*args, **kwargs):
        raise HostModelError('permission denied', 23)
    with pytest.raises(HostModelError):
        prioritize_raw_articles(index(), 1, [], tmp_path, 30, denied)


def test_no_time_does_not_call_native_or_claim_extra_articles_reviewed(tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('No remaining optional call budget')
    indexed = index()
    assert prioritize_raw_articles(indexed, 1, [], tmp_path, 0, forbidden) == indexed['shortlist']


def test_all_discovered_articles_keep_their_complete_original_body(tmp_path):
    from cwh_pipeline_runtime import atomic_write_json
    from prepare_cwh_corpus_index import prepare_corpus_index
    rows = [{**row, 'topic_hits': [1]} for row in articles()]
    corpus = {'candidates': rows}
    source = tmp_path / 'raw.json'
    atomic_write_json(source, corpus)
    target = prepare_corpus_index(source, corpus, ['公共服务'], shortlist_limit=1)
    indexed = json.loads(target.read_text('utf-8'))['topics'][0]
    assert len(indexed['discovery_shortlist']) == 2
    originals = {r['record_id']: r for r in rows}
    for card in indexed['discovery_shortlist']:
        assert json.loads(Path(card['full_text_path']).read_text('utf-8')) == originals[card['record_id']]
