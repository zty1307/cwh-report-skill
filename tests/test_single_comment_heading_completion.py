"""No invented titles, topic assignment, labels or formal-selection decisions."""
import copy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_comment_semantics import complete_single_comment_heading


def source():
    return {'topic_headings': {'2': '希望改善运动设施供给'}, 'rows': [
        {'id': 1, 'topic': 2, 'formal': True, 'label': 'positive', 'reason': '真实具体诉求'}]}


def test_only_single_selected_comment_uses_explicit_shared_heading():
    data = source()
    original = copy.deepcopy(data)
    result = complete_single_comment_heading(data)
    assert result['rows'][0]['heading'] == data['topic_headings']['2']
    assert result['transport_heading_completions'][0]['id'] == 1
    assert data == original


def test_multiple_selected_comments_do_not_inherit_one_shared_heading():
    data = source()
    data['rows'].append({**data['rows'][0], 'id': 2})
    result = complete_single_comment_heading(data)
    assert all('heading' not in row for row in result['rows'])
    assert 'transport_heading_completions' not in result


def test_nonempty_heading_no_shared_heading_and_excluded_decision_are_preserved():
    data = source()
    data['rows'][0]['heading'] = '原有非空标题'
    assert complete_single_comment_heading(data) == data
    data['rows'][0].pop('heading')
    data['topic_headings'] = {}
    assert complete_single_comment_heading(data) == data
    data['topic_headings'] = {'2': '不会用于排除评论'}
    data['rows'][0]['label'] = 'exclude'
    assert complete_single_comment_heading(data) == data
