"""An incomplete Markdown wrapper must not trigger a semantic retry."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_json_transport import single_fenced_json
from run_cwh_inline_review import response_object


@pytest.mark.parametrize('prefix', ['```json\n', '```JSON\r\n', '```\n'])
def test_complete_payload_needs_no_closing_markdown(prefix):
    expected = {'items': [{'id': 'w2', 'claim': '原文判断', 'claims': []}]}
    text = prefix + json.dumps(expected, ensure_ascii=False)
    for envelope in (text, json.dumps({'type': 'result', 'is_error': False, 'result': text})):
        result = response_object(envelope)
        assert result['items'] == expected['items']
        assert result['transport_repairs'] == [{
            'kind': 'decoded_complete_json_without_closing_markdown_fence',
            'original_text_sha256': hashlib.sha256(text.encode()).hexdigest()}]


@pytest.mark.parametrize('body', [
    '{"items":[]', '{"items":[{"id":"unfinished',
    '{"items":[],"items":[1]}', '{"items":[],"n":NaN}',
    '{"items":[]}\n{"items":[1]}', '{"items":[]}\n解释',
    '{"items":[]}\n```json\n{"items":[1]}',
    '{"items":[] "reason":"缺逗号"}', '[{"items":[]}]',
])
def test_missing_markdown_never_repairs_or_selects_json_content(body):
    text = '```json\n' + body
    assert single_fenced_json(text) is None
    with pytest.raises(ValueError):
        response_object(text)


def test_unknown_fence_language_is_not_json():
    assert single_fenced_json('```python\n{"items":[]}') is None
