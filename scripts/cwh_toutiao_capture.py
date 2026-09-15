"""Normalize retained, successful no-login Toutiao comment response envelopes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from cwh_pipeline_runtime import atomic_write_json
from cwh_weibo_capture import response, window, timestamp
from run_cwh_agent_reach_comment_collection import validate_comment_payload, iter_comment_objects, published_at, article_id
from run_cwh_sentiment_stage import stable_sample_id
from cwh_comment_filters import is_procedural_only


def normalize(observations, start, end):
    left, right = window(start, end)
    accepted, excluded, posts, captures, seen = [], [], {}, [], set()
    for check in observations['checks']:
        if check.get('source_id') != 'toutiao_public_comments' or check.get('status') != 'actual_comment_response_requires_normalization':
            continue
        path = Path(check['raw_file'])
        payload, digest = response(path)
        validate_comment_payload(payload)
        gid = article_id({'url': check['seed_url']})
        if str((payload.get('group') or {}).get('group_id')) != gid:
            raise ValueError('Comment response belongs to a different parent article')
        parent_id = 'toutiao-' + gid
        parent = payload.get('group') or {}
        title = (payload.get('repost_params') or {}).get('title') or ''
        if not title:
            raise ValueError('Parent title is unavailable; require a real parent-page capture')
        posts[parent_id] = {'id': parent_id, 'text': title, 'context_kind': 'api_parent_title_only',
            'source': parent.get('user_name') or '', 'published_at': '', 'url': check['seed_url'],
            'raw_file': str(path.resolve()), 'raw_sha256': digest}
        captures.append({'raw_file': str(path.resolve()), 'sha256': digest, 'more_pages_exposed': bool(payload['has_more']),
                         'visible_top_level_rows': len(payload['data'])})
        for comment, parent_comment in iter_comment_objects(payload):
            identity = str(comment.get('id_str') or comment.get('id'))
            row = {'platform': '今日头条', 'comment_id': identity, 'reply_id': identity if parent_comment else '',
                'parent_comment_id': parent_comment, 'text': comment['text'], 'source': comment.get('user_name', ''),
                'published_at': published_at(comment.get('create_time')), 'url': check['seed_url'],
                'like_count': comment.get('digg_count', 0), 'parent_post_id': parent_id,
                'parent_post_title': title, 'parent_post_source': posts[parent_id]['source'], 'parent_post_published_at': '',
                'raw_file': str(path.resolve()), 'raw_sha256': digest, 'raw_pointer': 'comment_id=' + identity,
                'topic': '', 'is_comment': True, 'semantic_review_completed': False}
            row['sample_id'] = stable_sample_id(row)
            reason = ''
            try:
                if not left <= timestamp(row['published_at']) <= right:
                    reason = 'outside_monitoring_window'
            except (ValueError, TypeError):
                reason = 'unparseable_comment_timestamp'
            if identity in seen:
                reason = 'duplicate_capture_of_same_comment_id'
            seen.add(identity)
            if not re.search(r'[A-Za-z0-9\u4e00-\u9fff]', re.sub(r'\[[^\]]*\]', '', row['text'])):
                reason = 'emoji_only_or_empty'
            if not reason and is_procedural_only(row['text']):
                reason = 'procedural_only'
            (excluded if reason else accepted).append({**row, 'exclusion_reason': reason} if reason else row)
    return {'schema_version': 1, 'monitoring_period': {'start': start, 'end': end}, 'rows': accepted,
            'excluded': excluded, 'posts': list(posts.values()), 'raw_captures': captures,
            'semantic_review_completed': False, 'topic_assignment_from_historical_seed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = normalize(json.loads(args.observations.read_text('utf-8-sig')), args.start, args.end)
    atomic_write_json(args.output, data)
    print(json.dumps({'rows': len(data['rows']), 'excluded': len(data['excluded']), 'posts': len(data['posts'])}))


if __name__ == '__main__':
    main()
