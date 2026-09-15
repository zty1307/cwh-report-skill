"""Exact provenance hints; semantic routing still belongs to the reviewer."""
import copy
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_heading_quality import cross_topic_shared_source_spans
from run_cwh_compiled_worker import independent_packet


def sample():
    text = '独立判断甲。共享机制与必要条件。独立判断乙。'
    sha = hashlib.sha256(text.encode()).hexdigest()
    snapshot = {'source_text': text, 'source_text_sha256': sha, 'snapshot_id': 'original'}
    topics, pools = [], []
    for number, (topic, start, end, claim) in enumerate([
        ('上位议题', 6, 16, '共享机制的判断'),
        ('具体议题', 0, 16, '增加独立判断甲及共享机制'),
    ], 1):
        evidence = {'evidence_id': f'real-{number}', 'candidate_id': f'c{number}',
                    'speaker_name': '原主体', 'speaker_role': '原职务', 'url': 'https://example.com/original',
                    'formal_claim': claim, 'source_excerpt': text[start:end],
                    'source_excerpt_start': start, 'source_excerpt_end': end}
        topics.append({'topic': topic, 'heading': topic, 'clusters': [{'summary': '原簇', 'evidence': [evidence]}]})
        pools.append({'topic': topic, 'candidates': [{'candidate_id': f'c{number}',
                      'source': '原来源', 'title': '原题名', 'source_snapshot': copy.deepcopy(snapshot)}]})
    return {'viewpoints': {'by_topic': topics}, 'research_audit': {'domestic_media_research': {
        'candidate_pool_by_topic': pools}}}


def test_shared_excerpt_hint_catches_different_length_claims_without_changing_data():
    data = sample()
    original = copy.deepcopy(data)
    hints = cross_topic_shared_source_spans(data)
    assert len(hints) == 1 and hints[0]['claim_ids'] == ['e1', 'e2']
    assert hints[0]['shared_original_span'] == [6, 16]
    assert hints[0]['scope'] == 'shared_original_span_hint_not_duplicate_verdict'
    assert data == original
    assert independent_packet(data)['cross_topic_shared_source_spans'] == hints
    assert not any('semantic_review' in ev for topic in data['viewpoints']['by_topic']
                   for cluster in topic['clusters'] for ev in cluster['evidence'])


def test_different_role_is_not_merged_by_name():
    data = sample()
    data['viewpoints']['by_topic'][1]['clusters'][0]['evidence'][0]['speaker_role'] = '其他职务'
    assert cross_topic_shared_source_spans(data) == []


def test_nonoverlapping_original_judgments_are_not_marked_shared():
    data = sample()
    evidence = data['viewpoints']['by_topic'][1]['clusters'][0]['evidence'][0]
    snapshot = data['research_audit']['domestic_media_research']['candidate_pool_by_topic'][1]['candidates'][0]['source_snapshot']
    evidence.update(source_excerpt_start=16, source_excerpt_end=len(snapshot['source_text']),
                    source_excerpt=snapshot['source_text'][16:])
    assert cross_topic_shared_source_spans(data) == []


def test_tampered_snapshot_or_unverified_coordinates_do_not_produce_hints():
    for mode in ('body', 'coordinate'):
        data = sample()
        if mode == 'body':
            data['research_audit']['domestic_media_research']['candidate_pool_by_topic'][1]['candidates'][0]['source_snapshot']['source_text'] += '变更'
        else:
            data['viewpoints']['by_topic'][1]['clusters'][0]['evidence'][0]['source_excerpt_start'] = True
        assert cross_topic_shared_source_spans(data) == []
