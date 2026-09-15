"""Narrow key-delimiter repair; evidence values and semantic gates unchanged."""
import json
import hashlib
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_json_transport import normalize_single_smart_quoted_member_key
from run_cwh_inline_review import response_object


def test_one_key_quote_pair_preserves_all_original_values_and_records_exact_positions():
    intended = {'review_method': 'ai_semantic_review', 'selected': [
        {'term': '服务供给', 'quote': '原文“服务供给”与英文\\"service\\"都保留', 'source_id': 'real-source-7'}]}
    raw = json.dumps(intended, ensure_ascii=False).replace('"review_method"', '“review_method”', 1)
    repaired = normalize_single_smart_quoted_member_key(raw)
    audit = repaired.pop('transport_repairs')
    assert repaired == intended
    assert audit == [{'kind': 'normalized_single_smart_quoted_member_key', 'positions': [1, 15],
                      'original_text_sha256': hashlib.sha256(raw.encode()).hexdigest()}]
    parsed = response_object(json.dumps({'type': 'result', 'is_error': False, 'result': raw}))
    assert parsed['selected'] == intended['selected']


def test_nested_single_member_key_keeps_container_shape_and_source_text():
    raw = '{"items":[{“source_id”:"real-9","content":"原文“判断”不能改"}]}'
    parsed = normalize_single_smart_quoted_member_key(raw)
    assert parsed['items'] == [{'source_id': 'real-9', 'content': '原文“判断”不能改'}]


@pytest.mark.parametrize('raw', [
    '{"items":[],"text":"原文“词”"}',
    '{“items”:[],“heading”:"甲"}',
    '{“items”:[] "heading":"甲"}',
    '{“items”:[],"heading":"未完',
    '{“items”:[],"items":[1]}',
    '{“items”:[],"nested":{"key":1,"key":2}}',
    '{“items”:}',
    '{“items”:[],"claim":“原文”}',
    '{“key-with-punctuation”:[]}',
    '{“it\\"ems”:[]}',
    '{“items":[]}',
])
def test_multiple_ambiguous_duplicate_truncated_or_already_valid_cases_are_not_repaired(raw):
    assert normalize_single_smart_quoted_member_key(raw) is None
