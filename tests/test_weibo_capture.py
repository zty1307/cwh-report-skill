import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_weibo_capture import normalize, plain_text, window


def fixture(tmp_path, rows, ok=1):
    post = {'id': 123, 'mblogid': 'AbC', 'user': {'id': 456, 'screen_name': '公开媒体'}, 'text_raw': '真实原帖', 'created_at': '2030-01-01'}
    (tmp_path / '123-post-response.json').write_text(json.dumps({'status': 200, 'body': json.dumps(post)}), encoding='utf-8')
    (tmp_path / '123-comments-response.json').write_text(json.dumps({'status': 200, 'body': json.dumps({'ok': ok, 'data': rows, 'total_number': 999})}), encoding='utf-8')
    path = tmp_path / 'collection_audit.json'
    path.write_text(json.dumps({'checks': [{'mid': '123', 'status': 'observed_public_comment_page', 'raw_file': '123-comments-response.json'}]}), encoding='utf-8')
    return path


def row(identity=1, **kwargs):
    return {'id': identity, 'text': '希望改善公共服务', 'created_at': '2030-01-01T08:00:00+08:00', 'user': {'screen_name': '网友'}, **kwargs}


def test_window_bot_emoji_and_no_search_topic_assignment(tmp_path):
    path = fixture(tmp_path, [row(), row(2, text='<img alt="[赞]"/>'),
        row(3, user={'screen_name': '平台助手', 'description': '平台AI账号'}), row(4, created_at='2030-01-02')])
    data = normalize([path], '2030-01-01', '2030-01-01')
    assert len(data['rows']) == 1
    assert data['rows'][0]['topic'] == '' and data['rows'][0]['semantic_review_completed'] is False
    assert {r['exclusion_reason'] for r in data['excluded']} == {'emoji_only_or_empty', 'explicitly_disclosed_automated_account', 'outside_monitoring_window'}
    assert data['raw_captures'][0]['reported_total_not_denominator'] == 999
    assert data['rows'][0]['raw_pointer'] == 'data[0]'


def test_reply_context_is_not_counted_twice_and_conflicting_ids_blocked(tmp_path):
    path = fixture(tmp_path, [row(comments=[row(2, reply_comment=row())]), row(1, text='edited')])
    data = normalize([path], '2030-01-01', '2030-01-01')
    assert [r['comment_id'] for r in data['rows']] == ['2']
    assert data['rows'][0]['parent_comment_id'] == '1'
    assert len(data['excluded']) == 2


def test_http_200_error_does_not_become_empty_success(tmp_path):
    path = fixture(tmp_path, [], ok=0)
    with pytest.raises(ValueError, match='successful'):
        normalize([path], '2030-01-01', '2030-01-01')


def test_markup_preserves_visible_emoji_and_actual_entities():
    assert plain_text('A&amp;B<img alt="[赞]"/><br>正文') == 'A&B[赞]\n正文'
    with pytest.raises(ValueError, match='precedes'):
        window('2030-01-02', '2030-01-01')
