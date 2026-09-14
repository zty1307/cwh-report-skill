import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_toutiao_capture import normalize
from cwh_comment_semantics import validate_capture_rows


def capture(tmp_path):
    gid = '7000000000000000001'
    raw = tmp_path / 'raw.json'
    payload = {'message': 'success', 'has_more': False, 'group': {'group_id': int(gid), 'user_name': '公开媒体'},
               'repost_params': {'title': '会议研究公共服务'}, 'data': [
        {'comment': {'id_str': '7000000000000000099', 'text': '建议增加公共服务供给', 'create_time': 1893456000, 'user_name': '网友'}}]}
    raw.write_text(json.dumps({'status': 200, 'body': json.dumps(payload)}), encoding='utf-8')
    observation = {'checks': [{'source_id': 'toutiao_public_comments', 'status': 'actual_comment_response_requires_normalization',
                    'seed_url': f'https://www.toutiao.com/article/{gid}/', 'raw_file': str(raw)}]}
    return normalize(observation, '2030-01-01', '2030-01-01'), raw


def test_fresh_raw_response_not_historical_labels_owns_comment(tmp_path):
    data, _ = capture(tmp_path)
    validate_capture_rows(data)
    assert len(data['rows']) == 1 and data['rows'][0]['topic'] == ''
    assert data['posts'][0]['context_kind'] == 'api_parent_title_only'
    data['rows'][0]['text'] = '伪造原话'
    with pytest.raises(ValueError, match='differs'):
        validate_capture_rows(data)


def test_changed_raw_capture_is_rejected(tmp_path):
    data, raw = capture(tmp_path)
    raw.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='changed'):
        validate_capture_rows(data)
