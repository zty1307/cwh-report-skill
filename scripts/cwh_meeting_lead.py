"""Carry a source-grounded current agenda into the fixed report opening."""
import json
import re
import unicodedata
from pathlib import Path

from cwh_meeting_intake import expected_date, validate_review


def text_key(text):
    # Ignore layout punctuation only, never substitute words, names or numbers.
    return ''.join(c for c in str(text) if not c.isspace()
                   and not unicodedata.category(c).startswith('P'))


def agenda_body(text):
    text = str(text).strip()
    text = re.sub(r'^[^，。\n]{1,60}主持召开国务院常务会议[，,。；;\s]*', '', text)
    text = re.sub(r'^会议[，,\s]*', '', text)
    return text.strip().rstrip('。')


def source_focus_fields(source, review):
    """News headline, not a concatenation of statistical topic labels.

    Called only after current communique/date validation. A short news title
    may be expanded with the first literal agenda item; no historical title,
    chair default, or guessed agenda is used.
    """
    title = re.sub(r'\s+', ' ', str(source.get('title') or '')).strip()
    match = re.search(r'[^\s，。:：|_]{2,20}主持召开国务院常务会议', title)
    if not match:
        return {}
    headline = title[match.start():].strip()
    suffix = headline[match.end() - match.start():].strip(' ，。:：')
    if not suffix:
        topics = review.get('topics') or []
        first = str(topics[0].get('title') or '') if topics else ''
        if not first.startswith(('听取', '研究', '审议', '部署', '进一步部署', '决定', '学习', '讨论')):
            return {}
        if text_key(first) not in text_key(source.get('source_text', '')):
            return {}
        headline += ' ' + first + ('等' if len(topics) > 1 else '')
    else:
        # A page-title website suffix is not part of the quoted news title.
        headline = re.split(r'__|\s*[|｜]\s*', headline, maxsplit=1)[0].strip()
    return {'focus_title': headline,
            'focus_source': source.get('url') or source['source_sha256']}


def report_agenda_fields(context_path, agenda, topics):
    """Optional enrichment: invalid context cannot stop otherwise usable output.

    The model has already understood the agenda. This function only verifies its
    current source/date/topic binding and carries literal wording into rendering;
    it does not synthesize a replacement agenda or certify semantic completeness.
    """
    if not context_path:
        return {}, {'status': 'not_provided'}
    focus_fields = {}
    try:
        context = json.loads(Path(context_path).read_text('utf-8-sig'))
        if context.get('status') != 'reviewed':
            raise ValueError('通稿未完成阅读审核')
        source, review = context['source'], context['review']
        validate_review({'expected_date': expected_date(agenda), 'sources': [source]}, review)
        if [row['title'] for row in review['topics']] != list(topics):
            raise ValueError('通稿议题与本期标准表不一致')
        # Source/date/topic binding certifies the current news headline
        # independently of whether an AI agenda summary is a literal span.
        focus_fields = source_focus_fields(source, review)
        body = agenda_body(review['meeting_summary'])
        key = text_key(body)
        if len(key) < 10 or not body.startswith(('听取', '研究', '审议', '部署', '进一步', '对', '决定', '学习', '讨论')):
            raise ValueError('会议概述不是完整议程动作表述')
        if key not in text_key(source['source_text']):
            raise ValueError('会议概述不能连续映射原文；保留原标题写法')
        for topic in review['topics']:
            first_sentence = re.split(r'[。！？\n]', topic['source_excerpt'], maxsplit=1)[0]
            anchors = [topic['title'], *topic['aliases'], agenda_body(first_sentence)]
            if not any(len(text_key(anchor)) >= 2 and text_key(anchor) in key for anchor in anchors):
                raise ValueError('会议概述未覆盖议题：' + topic['title'])
        return {**focus_fields,
                'agenda_text': body, 'agenda_source': source.get('url') or source['source_sha256'],
                'agenda_source_sha256': source['source_sha256']}, {
                    'status': 'source_mapped', 'source_sha256': source['source_sha256'],
                    'topic_count': len(topics), 'model_call_added': False,
                    'mapping': 'continuous_source_text_ignoring_layout_punctuation'}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return focus_fields, {'status': 'retained_topic_fallback', 'reason': str(exc),
                              'verified_focus_retained': bool(focus_fields)}
