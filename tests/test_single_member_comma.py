"""Lossless narrow framing repair; never semantic acceptance or value completion."""
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_json_transport import insert_single_missing_member_comma
from run_cwh_inline_review import response_object


def test_single_object_separator_preserves_all_existing_semantic_fields_and_unicode():
    intended = {'items': [{'id': 'original-id', 'claims': [{'claim': '资金支持有助于创新，但须控制风险。',
        'quote_range': ['original/1', 'original/3'], 'number': 12}]}],
        'clusters': [{'key': 'k1', 'heading': '认为资金支持须匹配研发周期', 'thin_reason': '仅有一主体'}]}
    raw = json.dumps(intended, ensure_ascii=False).replace(', "thin_reason"', ' "thin_reason"')
    repaired = insert_single_missing_member_comma(raw)
    audit = repaired.pop('transport_repairs')
    assert repaired == intended
    assert len(audit) == 1 and audit[0]['kind'] == 'inserted_single_missing_member_comma'
    result = response_object(json.dumps({'type': 'result', 'is_error': False, 'result': '```json\n' + raw + '\n```'}))
    assert result['items'] == intended['items'] and result['clusters'] == intended['clusters']


@pytest.mark.parametrize('raw', [
    '{"items": [], "heading": "未完',
    '{"items": [] "heading": "甲" "clusters": []}',
    '{"items": [] "heading": "甲", "heading": "乙"}',
    '{"items": [], "claims": ["甲" "乙"]}',
    '{"items": [], "heading": "包含空格 \\"thin_reason\\": 和逗号, 的完整字符串"}',
    '{"items": [] "heading": null',
])
def test_ambiguous_multiple_incomplete_array_or_valid_string_cases_are_not_repaired(raw):
    assert insert_single_missing_member_comma(raw) is None
