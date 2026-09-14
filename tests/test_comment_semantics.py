import copy
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_comment_semantics import compile_results, review_packet
from run_cwh_inline_review import response_object


def test_comment_output_parser_and_exact_id_coverage():
    assert response_object('{"rows":[]}') == {'rows': []}
    assert response_object('{"repairs":[]}') == {'repairs': []}
    capture = {'rows': [{'sample_id': 'real-id'}]}
    result = {'rows': [{'id': 1, 'topic': 1, 'label': 'positive', 'formal': True, 'reason': '支持扩大公共服务覆盖', 'heading': '建议扩大覆盖'}],
              'topic_headings': {'1': '建议扩大覆盖'}}
    reviewed = compile_results(capture, ['公共服务'], result, {'session_id': 'actual-run'})
    assert reviewed[0]['sample_id'] == 'real-id' and reviewed[0]['reviewer_run_id'] == 'actual-run'
    assert reviewed[0]['topic'] == '公共服务'
    result['rows'][0]['id'] = 2
    with pytest.raises(ValueError, match='every supplied ID'):
        compile_results(capture, ['公共服务'], result, {'session_id': 'actual-run'})


@pytest.mark.parametrize('changes', [{'topic': 0}, {'formal': 'true'}, {'label': 'unreviewed'}, {'reason': ''}])
def test_invalid_results_cannot_create_handoff(changes):
    row = {'id': 1, 'topic': 1, 'label': 'neutral', 'formal': False, 'reason': '具体问题询问', 'heading': ''}
    row.update(changes)
    with pytest.raises(ValueError):
        compile_results({'rows': [{'sample_id': 'real'}]}, ['topic'], {'rows': [row]}, {'session_id': 'real-run'})


def test_parent_title_is_not_misrepresented_as_full_body():
    capture = {'rows': [{'parent_post_id': 'p1', 'text': '具体意见'}], 'posts': [
        {'id': 'p1', 'text': '原帖标题', 'source': '媒体', 'published_at': '', 'context_kind': 'api_parent_title_only'}]}
    assert review_packet(capture, ['topic'])['posts'][0]['context_kind'] == 'api_parent_title_only'
