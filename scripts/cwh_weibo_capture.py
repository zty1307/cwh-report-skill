"""Normalize retained public Weibo responses; never infer topic or sentiment.

Input is an authorized collector's audit and unmodified response envelopes.
No network, cookies, credentials, or platform account actions are used here.
"""
from __future__ import annotations
import argparse
from datetime import datetime, time as day_time
from email.utils import parsedate_to_datetime
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from cwh_pipeline_runtime import atomic_write_json
from run_cwh_sentiment_stage import stable_sample_id


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'img':
            self.parts.append(values.get('alt', ''))
        elif tag == 'br':
            self.parts.append('\n')


def plain_text(value):
    parser = PlainText()
    parser.feed(str(value or ''))
    return ''.join(parser.parts).strip()


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
    return parsed


def window(start, end):
    left, right = timestamp(start), timestamp(end)
    if len(end) == 10:
        right = datetime.combine(right.date(), day_time.max, tzinfo=right.tzinfo)
    if right < left:
        raise ValueError('Monitoring end precedes start')
    return left, right


def response(path):
    data = path.read_bytes()
    envelope = json.loads(data.decode('utf-8-sig'))
    if envelope.get('status') != 200:
        raise ValueError(f'Unsuccessful HTTP response: {path.name}')
    return json.loads(envelope['body']), hashlib.sha256(data).hexdigest()


def explicit_automated_account(user):
    # Only explicit account disclosures; do not infer bots from tone or speed.
    description = str(user.get('description') or '')
    reason = str(user.get('verified_reason') or '')
    return bool(re.search(r'AI\s*(?:账号|机器人)|人工智能(?:账号|助手)|自动回复机器人', description, re.I)
                or re.search(r'AI\s*(?:账号|机器人)|人工智能(?:账号|助手)', reason, re.I))


def flatten(rows, prefix='data', parent=''):
    for index, row in enumerate(rows):
        pointer = f'{prefix}[{index}]'
        yield row, pointer, parent
        # reply_comment is quoted parent context, not another captured reply.
        children = row.get('comments') or []
        if isinstance(children, list):
            yield from flatten(children, pointer + '.comments', str(row.get('idstr') or row.get('id') or ''))


def normalize(audit_paths, start, end):
    left, right = window(start, end)
    rows, excluded, sources, captures, seen = [], [], {}, [], {}
    for audit_path in audit_paths:
        audit_path = Path(audit_path).resolve()
        audit = json.loads(audit_path.read_text('utf-8-sig'))
        for check in audit['checks']:
            if check.get('status') != 'observed_public_comment_page':
                continue
            mid = str(check['mid'])
            post_path = audit_path.parent / f'{mid}-post-response.json'
            post, post_hash = response(post_path)
            if str(post.get('idstr') or post.get('id')) != mid:
                raise ValueError('Post identity does not match collection audit')
            user = post.get('user') or {}
            if not user.get('id') or not re.fullmatch(r'[A-Za-z0-9]+', str(post.get('mblogid') or '')):
                raise ValueError('Missing public post identity')
            url = f'https://weibo.com/{user["id"]}/{post["mblogid"]}'
            sources[mid] = {'id': mid, 'text': post.get('text_raw') or plain_text(post.get('text')),
                            'source': user.get('screen_name', ''), 'published_at': post.get('created_at'),
                            'url': url, 'raw_file': str(post_path), 'raw_sha256': post_hash}
            for raw_name in check.get('raw_files') or [check['raw_file']]:
                # Capture members stay with the audit, independent of old cwd.
                raw_path = audit_path.parent / Path(raw_name).name
                body, digest = response(raw_path)
                if body.get('ok') != 1 or not isinstance(body.get('data'), list):
                    raise ValueError('No successful public comment array')
                captures.append({'raw_file': str(raw_path), 'sha256': digest,
                                 'visible_top_level_rows': len(body['data']),
                                 'reported_total_not_denominator': body.get('total_number'),
                                 'more_pages_exposed': bool(body.get('max_id'))})
                for item, pointer, parent in flatten(body['data']):
                    identity = str(item.get('idstr') or item.get('id') or '')
                    text = item.get('text_raw') or plain_text(item.get('text'))
                    account = item.get('user') or {}
                    row = {'platform': '微博', 'comment_id': identity, 'reply_id': identity if parent else '',
                           'parent_comment_id': parent, 'text': text, 'source': account.get('screen_name', ''),
                           'published_at': item.get('created_at', ''), 'url': url,
                           'like_count': item.get('like_count', 0), 'parent_post_id': mid,
                           'parent_post_title': sources[mid]['text'], 'parent_post_source': sources[mid]['source'],
                           'parent_post_published_at': sources[mid]['published_at'],
                           'raw_file': str(raw_path), 'raw_sha256': digest, 'raw_pointer': pointer,
                           'topic': '', 'is_comment': True, 'semantic_review_completed': False}
                    row['sample_id'] = stable_sample_id(row)
                    reason = ''
                    try:
                        published = timestamp(row['published_at'])
                        row['published_at'] = published.isoformat()
                        if not left <= published <= right:
                            reason = 'outside_monitoring_window'
                    except (ValueError, TypeError, OverflowError):
                        reason = 'unparseable_comment_timestamp'
                    if not identity or not re.fullmatch(r'\d+', identity):
                        reason = 'missing_comment_identity'
                    elif explicit_automated_account(account):
                        reason = 'explicitly_disclosed_automated_account'
                    elif not re.search(r'[A-Za-z0-9\u4e00-\u9fff]', re.sub(r'\[[^\]]*\]', '', text)):
                        reason = 'emoji_only_or_empty'
                    if identity in seen:
                        reason = 'duplicate_capture_of_same_comment_id'
                        if seen[identity] != text:
                            reason = 'same_comment_id_changed_text_requires_review'
                    else:
                        seen[identity] = text
                    if reason:
                        excluded.append({**row, 'exclusion_reason': reason})
                    else:
                        rows.append(row)
    # Conflicting captures cannot silently leave the first version eligible.
    conflict_ids = {r['comment_id'] for r in excluded if r['exclusion_reason'] == 'same_comment_id_changed_text_requires_review'}
    if conflict_ids:
        kept = []
        for row in rows:
            if row['comment_id'] in conflict_ids:
                excluded.append({**row, 'exclusion_reason': 'same_comment_id_changed_text_requires_review'})
            else:
                kept.append(row)
        rows = kept
    return {'schema_version': 1, 'monitoring_period': {'start': start, 'end': end},
            'rows': rows, 'excluded': excluded, 'posts': list(sources.values()), 'raw_captures': captures,
            'semantic_review_completed': False, 'topic_assignment_from_search_queries': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection-audit', action='append', required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = normalize(args.collection_audit, args.start, args.end)
    atomic_write_json(Path(args.output), result)
    print(json.dumps({'pending_semantic_review': len(result['rows']), 'excluded': len(result['excluded']),
                      'posts': len(result['posts']), 'output': args.output}, ensure_ascii=False))


if __name__ == '__main__':
    main()
