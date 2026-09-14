import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_host_compiler import compiled
from cwh_review_repair import (
    request, apply, validate_identity, combine, validate_combined, evidence_rows,
    apply_reviewer_narrowing, reviewer_narrowing_packet,
)
from domestic_evidence_mapping import validate_semantic_review_packet
from run_cwh_compiled_worker import compile_review


def packets():
    analysis = compiled()
    first = evidence_rows(analysis)[0][1]
    second = copy.deepcopy(first)
    second['evidence_id'] += '-second'
    analysis['viewpoints']['by_topic'][0]['clusters'][0]['evidence'].append(second)
    initial = {'review_version': '1.0', 'review_pass': 'independent_second_pass', 'reviewer_run_id': 'real-first',
               'source_bundle_sha256': 'original-hash', 'reviews': [
        {'evidence_id': first['evidence_id'], 'verdict': 'fully_supported', 'reviewed_by': 'configured_model:real-first',
         'reviewed_at': 'time', 'rationale': 'original reason', 'propositions': [{'text': 'unchanged'}]},
        {'evidence_id': second['evidence_id'], 'verdict': 'partially_supported', 'reviewed_by': 'configured_model:real-first',
         'reviewed_at': 'time', 'rationale': 'range insufficient', 'propositions': [{'text': 'requires repair'}]}]}
    return analysis, initial, second['evidence_id']


def test_repair_only_rejected_fields_and_no_self_certification():
    analysis, initial, identity = packets()
    packet = request(analysis, initial)
    assert [r['id'] for r in packet['claims']] == [identity]
    patch = {'repairs': [{'id': identity, 'formal_claim': '应按实际需求调整公共服务。', 'quote_range': [1, 1]}]}
    revised = apply(analysis, packet, patch)
    validate_identity(analysis, revised, {identity})
    assert 'semantic_review' not in evidence_rows(revised)[1][1]
    assert evidence_rows(analysis)[1][1]['formal_claim'] != patch['repairs'][0]['formal_claim']
    evidence_rows(revised)[0][1]['formal_claim'] = 'unauthorized'
    with pytest.raises(ValueError, match='accepted claim'):
        validate_identity(analysis, revised, {identity})


def test_repair_rejects_source_edits_and_wrong_coverage():
    analysis, initial, identity = packets()
    packet = request(analysis, initial)
    with pytest.raises(ValueError, match='exactly'):
        apply(analysis, packet, {'repairs': []})
    with pytest.raises(ValueError, match='only'):
        apply(analysis, packet, {'repairs': [{'id': identity, 'formal_claim': 'text', 'quote_range': [1, 1], 'source': 'fake'}]})
    revised = copy.deepcopy(analysis)
    evidence_rows(revised)[1][1]['speaker_name'] = 'fake'
    with pytest.raises(ValueError, match='frozen source'):
        validate_identity(analysis, revised, {identity})


def test_combined_review_preserves_rejection_and_actual_run_ids():
    analysis, initial, identity = packets()
    later = {**initial, 'reviewer_run_id': 'real-second', 'reviews': [copy.deepcopy(initial['reviews'][1])]}
    packet = combine(analysis, initial, later, {identity}, 'new-hash')
    validate_combined(analysis, analysis, initial, packet)
    assert packet['reviews'][1]['verdict'] == 'partially_supported'
    assert packet['reviews'][0]['reviewer_run_id'] == 'real-first'
    assert any(i['code'] == 'review_not_fully_supported' for i in validate_semantic_review_packet(analysis, packet, source_bundle_sha256='new-hash'))
    packet['reviews'][0]['rationale'] = 'rewritten'
    with pytest.raises(ValueError, match='unchanged verdict'):
        validate_combined(analysis, analysis, initial, packet)


def test_repair_author_cannot_be_independent_reviewer():
    analysis, initial, identity = packets()
    later = {**initial, 'reviewer_run_id': 'author-repair', 'reviews': [copy.deepcopy(initial['reviews'][1])]}
    packet = combine(analysis, initial, later, {identity}, 'new-hash')
    packet['repair_provenance']['author_repair_run_id'] = 'author-repair'
    assert any(i['code'] == 'reviewer_not_independent' for i in validate_semantic_review_packet(analysis, packet, source_bundle_sha256='new-hash'))


def test_one_pass_reviewer_narrowing_preserves_rejection_and_certifies_replacement():
    analysis = compiled()
    replacement = '公共服务建设应结合实际需求完善设施布局、运行维护和长效评估机制，稳步提升服务可及性与资源使用效率。'
    raw = {'reviews': [{
        'id': 'e1',
        'verdict': 'partially_supported',
        'rationale': '原观点含有原文未支持的程度词。',
        'revision': {
            'formal_claim': replacement,
            'verdict': 'fully_supported',
            'rationale': '收窄后的判断均可由连续原文支持。',
        },
    }]}
    run = {'session_id': 'independent-reviewer', 'completed_at': 'time'}
    initial = compile_review(analysis, raw, run, 'original-hash')
    repaired, revisions = apply_reviewer_narrowing(analysis, raw)
    final = reviewer_narrowing_packet(repaired, initial, raw, revisions, run, 'repaired-hash')
    validate_combined(analysis, repaired, initial, final)
    assert evidence_rows(repaired)[0][1]['formal_claim'] == replacement
    assert final['reviews'][0]['verdict'] == 'fully_supported'
    assert final['repair_provenance']['revisions'][0]['original_verdict'] == 'partially_supported'

    final['repair_provenance']['revisions'][0]['formal_claim'] = '篡改'
    with pytest.raises(ValueError, match='differs'):
        validate_combined(analysis, repaired, initial, final)
