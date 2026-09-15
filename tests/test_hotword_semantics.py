import copy
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


def test_packet_preserves_only_actual_support_and_current_topics():
    topics, docs, _ = fixture()
    packet = author_packet(topics, docs)
    assert packet['sources'][0]['excerpts'] == docs[0]['excerpts']
    assert list(packet['topics'].values()) == topics
    assert all('content' not in d and 'url' not in d for d in packet['sources'])


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
