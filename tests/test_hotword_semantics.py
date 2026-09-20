import copy
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_hotword_semantics import compile_selection, finish, author_packet, evidence_documents


def fixture():
    topics = ['水环境治理', '养老服务']
    documents = [
        {'id': 'd1', 'content': '需要加强污水处理，完善排水管网。', 'excerpts': ['需要加强污水处理，完善排水管网。'],
         'title': '水环境治理建议', 'source': '来源甲', 'url': 'https://example.test/a', 'topic_hits': [1], 'is_comment': False},
        {'id': 'd2', 'content': '完善社区养老服务。', 'excerpts': ['完善社区养老服务。'],
         'title': '养老服务建议', 'source': '来源乙', 'url': 'https://example.test/b', 'topic_hits': [2], 'is_comment': False}]
    rows = [{'term': term, 'source_ids': [f'd{n}'], 'evidence_aliases': [], 'topic_hits': [n],
             'semantic_type': 'policy_tool', 'standalone_topic_label': True,
             'selection_reason': 'unit fixture', 'ai_representativeness': '中'}
            for n, term in enumerate(['污水处理', '社区养老'], 1)]
    return topics, documents, {'selected': rows}


def test_available_selection_quarantines_bad_word_without_changing_valid_decisions():
    from cwh_hotword_semantics import compile_available_selection
    topics, docs, decision = fixture()
    original = copy.deepcopy(decision)
    decision['selected'].append({**decision['selected'][0], 'term': '虚构热词', 'evidence_aliases': []})
    selected, quarantined = compile_available_selection(topics, docs, decision)
    assert [r['term'] for r in selected] == [r['term'] for r in original['selected']]
    assert len(quarantined) == 1 and quarantined[0]['input_index'] == 2
    assert quarantined[0]['semantic_verdict'] == 'not_certified'
    assert decision['selected'][:2] == original['selected']
    assert [r['id'] for r in selected] == ['w1', 'w2']
    with pytest.raises(ValueError):
        compile_selection(topics, docs, decision, minimum=1)
    with pytest.raises(ValueError):
        compile_available_selection(topics, docs, {'selected': [decision['selected'][-1]]})


def test_available_selection_does_not_invent_second_pass_approval():
    from cwh_hotword_semantics import compile_available_selection
    topics, docs, decision = fixture()
    decision['selected'].append(copy.deepcopy(decision['selected'][0]))
    selected, quarantined = compile_available_selection(topics, docs, decision)
    assert quarantined[-1]['host_gate_error'] == 'Duplicate hotword'
    with pytest.raises(ValueError, match='fresh model run'):
        finish(topics, docs, selected, {'reviews': []}, {'session_id': 'same'}, {'session_id': 'same'}, minimum=1)


def test_packet_preserves_only_actual_support_and_current_topics():
    topics, docs, _ = fixture()
    packet = author_packet(topics, docs)
    assert packet['sources'][0]['excerpts'] == docs[0]['excerpts']
    assert list(packet['topics'].values()) == topics
    assert all('content' not in d and 'url' not in d for d in packet['sources'])


def test_contextual_concern_keeps_true_labels_and_still_needs_actual_topic_evidence(tmp_path):
    topics, docs, decision = fixture()
    docs[0]['excerpts'] = ['水环境治理需要明确资金来源。']
    docs[0]['content'] = docs[0]['excerpts'][0]
    row = decision['selected'][0]
    row.update(term='资金来源', standalone_topic_label=False, contextual_topic_label=True,
               selection_reason='明确指水环境治理项目的资金来源，不是泛指所有资金')
    selected = compile_selection(topics, docs, decision, minimum=2, maximum=2)
    assert selected[0]['evidence_tier'] == 'supporting'
    assert selected[0]['standalone_topic_label'] is False
    reviews = {'reviews': [{'id': r['id'], 'keep': True, 'reason': '原话及议题支持'} for r in selected]}
    final = finish(topics, docs, selected, reviews, {'session_id': 'a'}, {'session_id': 'b'}, minimum=2, maximum=2)
    concern = next(r for r in final['selected'] if r['term'] == '资金来源')
    assert concern['contextual_topic_label'] is True and concern['standalone_topic_label'] is False
    # The reviewed pipeline output must remain valid at the report boundary.
    # Previously the renderer rejected every contextual supporting term.
    from formalize_cwh_report import apply_hotword_audit
    path = tmp_path / 'hotword_audit.json'
    audit = {**final, 'status': 'ai_review_complete',
             'method': 'ai_semantic_review_with_evidence', 'settings': {'minimum_term_count': 2}}
    path.write_text(json.dumps(audit), encoding='utf-8')
    data = {'meeting': {'topics': topics}}
    apply_hotword_audit(data, path)
    rendered = next(r for r in data['hotwords'] if r['word'] == '资金来源')
    assert rendered['contextual_topic_label'] is True
    assert rendered['standalone_topic_label'] is False
    assert rendered['evidence_tier'] == 'supporting'
    for mutation in ({'evidence_tier': 'core'}, {'contextual_topic_label': False},
                     {'ai_reviewed': False}, {'document_count': 0}):
        invalid = copy.deepcopy(audit)
        next(r for r in invalid['selected'] if r['term'] == '资金来源').update(mutation)
        path.write_text(json.dumps(invalid), encoding='utf-8')
        with pytest.raises(ValueError, match='证据门禁'):
            apply_hotword_audit({'meeting': {'topics': topics}}, path)
    row['topic_hits'] = [2]
    with pytest.raises(ValueError, match='topic has no cited source'):
        compile_selection(topics, docs, decision, minimum=2, maximum=2)


def test_contextual_flag_is_not_a_core_label_or_missing_semantics_bypass():
    from cwh_hotword_pipeline import apply_hotword_ai_review
    topics, docs, decision = fixture()
    selected = compile_selection(topics, docs, decision, minimum=2, maximum=2)
    selected[0].update(standalone_topic_label=False, contextual_topic_label=True, evidence_tier='core')
    review = {'review_method': 'ai_semantic_review', 'second_pass_completed': True, 'selected': selected}
    with pytest.raises(ValueError, match='standalone'):
        apply_hotword_ai_review(review, [], docs, topics, [[t] for t in topics], minimum_term_count=2, target_term_count=2)
    selected[0].update(evidence_tier='supporting', contextual_topic_label=False)
    with pytest.raises(ValueError, match='standalone'):
        apply_hotword_ai_review(review, [], docs, topics, [[t] for t in topics], minimum_term_count=2, target_term_count=2)


@pytest.mark.parametrize('mutation', ['fake_id', 'absent_quote', 'wrong_topic', 'fake_alias', 'duplicate', 'bool_topic'])
def test_selection_blocks_invented_mapping_and_bad_types(mutation):
    topics, docs, decision = fixture()
    row = decision['selected'][0]
    if mutation == 'fake_id': row['source_ids'] = ['nonexistent']
    if mutation == 'absent_quote': row['term'] = '数字农业'
    if mutation == 'wrong_topic': row['topic_hits'] = [2]
    if mutation == 'fake_alias': row['evidence_aliases'] = ['原文未说的话']
    if mutation == 'duplicate': decision['selected'][1] = copy.deepcopy(row)
    if mutation == 'bool_topic': row['topic_hits'] = [True]
    with pytest.raises(ValueError):
        compile_selection(topics, docs, decision, minimum=2, maximum=2)


def test_second_pass_is_real_complete_and_preserves_rejections():
    topics, docs, decision = fixture()
    selected = compile_selection(topics, docs, decision, minimum=2, maximum=2)
    reviews = {'reviews': [{'id': r['id'], 'keep': True, 'reason': 'unit fixture'} for r in selected]}
    author, reviewer = {'session_id': 'author'}, {'session_id': 'reviewer'}
    result = finish(topics, docs, selected, reviews, author, reviewer, minimum=2, maximum=2)
    assert result['second_pass_completed'] is True
    assert {r['document_count'] for r in result['selected']} == {1}
    assert result['review_provenance']['reviewer_run'] == reviewer
    with pytest.raises(ValueError, match='fresh model run'):
        finish(topics, docs, selected, reviews, author, author, minimum=2, maximum=2)
    reviews['reviews'][0]['keep'] = False
    with pytest.raises(ValueError, match='rejected'):
        finish(topics, docs, selected, reviews, author, reviewer, minimum=2, maximum=2)
    reviews['reviews'].pop()
    with pytest.raises(ValueError, match='every selected ID'):
        finish(topics, docs, selected, reviews, author, reviewer, minimum=2, maximum=2)


def test_unreviewed_viewpoints_cannot_enter_hotword_model():
    from test_host_compiler import compiled
    with pytest.raises(ValueError, match='independently verified'):
        evidence_documents(compiled(), [])

def test_available_hotwords_allow_shortfall_but_preserve_second_pass_and_source_checks():
    topics, docs, decision = fixture()
    decision['selected'] = decision['selected'][:1]
    selected = compile_selection(topics, docs, decision, minimum=1, require_coverage=False)
    reviewed = {'reviews': [{'id': selected[0]['id'], 'keep': True, 'reason': 'real support'}]}
    result = finish(topics, docs, selected, reviewed, {'session_id': 'a'}, {'session_id': 'b'},
                    minimum=1, deliver_available=True)
    assert len(result['selected']) == 1
    assert result['count_shortfall']['actual_count'] == 1
    assert result['second_pass_completed'] is True
    with pytest.raises(ValueError, match='fresh model run'):
        finish(topics, docs, selected, reviewed, {'session_id': 'a'}, {'session_id': 'a'},
               minimum=1, deliver_available=True)
    decision['selected'][0]['term'] = '无证据词条'
    with pytest.raises(ValueError, match='literal support'):
        compile_selection(topics, docs, decision, minimum=1, require_coverage=False)


def test_recovered_review_clears_only_stale_missing_cloud_flag(tmp_path):
    from formalize_cwh_report import apply_hotword_audit
    topics, docs, decision = fixture()
    selected = compile_selection(topics, docs, decision, minimum=1, require_coverage=False)
    reviews = {'reviews': [{'id': r['id'], 'keep': True, 'reason': '原文支持'} for r in selected]}
    audit = finish(topics, docs, selected, reviews, {'session_id': 'a'}, {'session_id': 'b'},
                   minimum=1, deliver_available=True)
    path = tmp_path / 'recovered.json'
    path.write_text(json.dumps(audit), encoding='utf-8')
    missing = '旧热词审核缺口'
    data = {'meeting': {'topics': topics}, 'hotwords': [], 'hotword_review_gap': missing,
            'audit': {'data_gaps': [missing, '其他缺口'],
                      'acceptance': {'ready_for_formal_delivery': False, 'blockers': [missing, '其他缺口']}}}
    apply_hotword_audit(data, path)
    assert 'hotword_review_gap' not in data
    assert len(data['hotwords']) == 2
    assert missing not in data['audit']['data_gaps']
    assert '其他缺口' in data['audit']['acceptance']['blockers']
    assert data['audit']['acceptance']['ready_for_formal_delivery'] is False
    assert data['audit']['resolved_data_gaps'][0]['notice'] == missing


def test_rejected_recovery_does_not_clear_missing_cloud_flag(tmp_path):
    from formalize_cwh_report import apply_hotword_audit
    path = tmp_path / 'invalid.json'
    path.write_text(json.dumps({'status': 'ai_review_complete', 'method': 'ai_semantic_review_with_evidence',
                               'second_pass_completed': False}), encoding='utf-8')
    data = {'hotword_review_gap': '仍然缺失', 'hotwords': []}
    with pytest.raises(ValueError):
        apply_hotword_audit(data, path)
    assert data == {'hotword_review_gap': '仍然缺失', 'hotwords': []}
