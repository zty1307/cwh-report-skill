import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_json_transport import escape_cjk_internal_quotes


@pytest.mark.parametrize('value', [
    '原话中的"会议"仍需明确。',
    '原文"更加谨慎""保留条件"均须核验。',
    '原文"结构转型""K型分化"均须核验。',
    '讨论去年的"924"政策范围。',
    '需说明："具体条件"，不得扩大。',
])
def test_internal_quote_runs_preserve_all_decoded_characters(value):
    raw = '{"reviews":[{"id":"e1","verdict":"unsupported","rationale":"' + value + '"}]}'
    result = escape_cjk_internal_quotes(raw)
    assert result is not None
    assert result['reviews'] == [{'id': 'e1', 'verdict': 'unsupported', 'rationale': value}]
    repair = result['transport_repairs'][0]
    assert repair['original_text_sha256']
    fixed = raw
    for index in reversed(repair['positions']):
        fixed = fixed[:index] + '\\' + fixed[index:]
    assert json.loads(fixed) == {'reviews': result['reviews']}


@pytest.mark.parametrize('raw', [
    '{"reviews":[] "note":"讨论"会议"范围"}',
    '{"reviews":[],"reviews":[],"note":"讨论"会议"范围"}',
    '{"reviews":[],"number":NaN,"note":"讨论"会议"范围"}',
    '{"reviews":[],"note":"讨论"会议"范围',
    '{"bad"键":"值","note":"讨论"会议"范围"}',
    '{"reviews":[],"note":"ASCII "words" only"}',
])
def test_ambiguous_structure_duplicates_and_truncation_still_fail(raw):
    assert escape_cjk_internal_quotes(raw) is None
