import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_json_transport import remove_single_stray_period_before_string_value


def test_one_period_removed_without_changing_quoted_value_or_any_other_field():
    text = '{"items":[{"id":."actual-id","reason":"原文.保持不变","include":false}]}'
    result = remove_single_stray_period_before_string_value(text)
    assert result['items'] == [{'id': 'actual-id', 'reason': '原文.保持不变', 'include': False}]
    assert result['transport_repairs'] == [{
        'kind': 'removed_single_stray_period_before_string_value', 'position': text.index('."'),
        'original_text_sha256': hashlib.sha256(text.encode()).hexdigest()}]


@pytest.mark.parametrize('text', [
    '{"items":[{"id":".actual-id"}]}',
    '{"items":[{"id":.2}]}',
    '{"items":[{."id":"actual-id"}]}',
    '{"items":[{"id":.."actual-id"}]}',
    '{"items":[{"id":."actual-id","reason":."second-defect"}]}',
    '{"items":[{"id":."actual-id","id":"duplicate"}]}',
    '{"items":[{"id":."actual-id","reason":"truncated}',
    '{"items":[{"id":."actual-id","decision":"excluded":"missing-field"}]}',
    '{"items":[{"id":."actual-id","number":NaN}]}',
])
def test_valid_strings_numbers_keys_duplicates_and_other_defects_are_not_repaired(text):
    assert remove_single_stray_period_before_string_value(text) is None
