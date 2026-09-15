"""Synthetic contract tests; not vendor-model end-to-end evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import raw_system_workbook_pipeline as pipeline


def inputs(count=100):
    return [{'source_row': i, 'account': f'account-{i // 20}',
             'title': 'anchor topic', 'content': 'anchor topic original body',
             'url': f'https://example.test/{i}', 'read_count': 10000-i}
            for i in range(count)]


def reviewed(packet):
    return {'review_method': 'ai_semantic_review', 'items': [
        {'record_id': row['record_id'], 'decision': 'include', 'topic_hits': [1],
         'review_reason': 'Focused original body', 'classification_confidence': .9}
        for row in packet['items']]}


CONFIG = {'meeting_anchor_patterns': ['anchor'], 'public_roundup_patterns': [], 'public_top_n': 10}
META = {'topic_titles': ['topic'], 'topic_aliases': [['topic']]}


def test_refill_adds_real_candidates_and_terminates_at_fixed_limit():
    rows = inputs()
    original = copy.deepcopy(rows)
    result = pipeline.filter_public_top(rows, CONFIG, META)
    assert len(result['review_packet']['items']) == 30
    for size in (60, 90):
        result = pipeline.filter_public_top(rows, CONFIG, META, review=reviewed(result['review_packet']))
        assert result['status'] == 'ai_review_expand_required'
        assert len(result['review_packet']['items']) == size
    result = pipeline.filter_public_top(rows, CONFIG, META, review=reviewed(result['review_packet']))
    assert result['status'] == 'ai_review_complete'
    assert result['evidence_shortfall']['reason'] == 'candidate_limit_reached'
    assert result['evidence_shortfall']['actual'] == 5
    assert result['evidence_shortfall']['reviewed_candidates'] == 90
    assert rows == original


def test_actual_exhaustion_keeps_short_result_without_repeated_review():
    rows = inputs(8)
    packet = pipeline.filter_public_top(rows, CONFIG, META)['review_packet']
    result = pipeline.filter_public_top(rows, CONFIG, META, review=reviewed(packet))
    assert result['status'] == 'ai_review_complete'
    assert result['evidence_shortfall']['reason'] == 'candidates_exhausted'
    assert len(result['selected']) == 1


def test_new_batch_can_complete_ten_real_sources():
    rows = inputs(60)
    for i, row in enumerate(rows[30:], 30):
        row['account'] = f'new-{i}'
    packet = pipeline.filter_public_top(rows, CONFIG, META)['review_packet']
    first = pipeline.filter_public_top(rows, CONFIG, META, review=reviewed(packet))
    assert first['status'] == 'ai_review_expand_required'
    result = pipeline.filter_public_top(rows, CONFIG, META, review=reviewed(first['review_packet']))
    assert result['status'] == 'ai_review_complete'
    assert len(result['selected']) == 10 and result['evidence_shortfall'] is None


def test_ranking_gap_is_propagated_only_for_hash_bound_workbook(tmp_path):
    from formalize_cwh_report import apply_raw_public_top_audit
    workbook = tmp_path / 'standard.xlsx'
    workbook.write_bytes(b'owned fixture workbook')
    folder = tmp_path / 'run'
    folder.mkdir()
    payload = {'workbook_sha256': hashlib.sha256(workbook.read_bytes()).hexdigest(),
               'evidence_shortfall': {'actual': 6, 'required': 10}}
    (folder / 'public_top_audit.json').write_text(json.dumps(payload), encoding='utf-8')
    data = {'collection': {'system_workbook': str(workbook)}, 'audit': {'acceptance': {'ready_for_formal_delivery': True}}}
    apply_raw_public_top_audit(data)
    apply_raw_public_top_audit(data)
    assert not data['audit']['acceptance']['ready_for_formal_delivery']
    assert len(data['audit']['acceptance']['blockers']) == 1
    workbook.write_bytes(b'changed workbook')
    other = {'collection': {'system_workbook': str(workbook)}}
    apply_raw_public_top_audit(other)
    assert 'audit' not in other
