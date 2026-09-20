import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_public_reader import decode_public_html


@pytest.mark.parametrize('declared', ['gb2312', 'gbk', 'cp936'])
def test_legacy_chinese_label_accepts_strict_superset_without_replacement(declared):
    original = '原文含生僻字𠮷，不能丢失。'
    decoded, actual = decode_public_html(original.encode('gb18030'), declared)
    assert decoded == original
    assert actual == 'gb18030'
    assert '\ufffd' not in decoded


def test_valid_declared_utf8_is_not_changed():
    assert decode_public_html('完整原文'.encode(), 'utf-8') == ('完整原文', 'utf-8')


def test_unicode_bom_is_authoritative_and_removed():
    assert decode_public_html('原文'.encode('utf-8-sig'), 'gb2312') == ('原文', 'utf-8-sig')


@pytest.mark.parametrize('declared', ['utf-8', 'gbk'])
def test_corrupt_bytes_are_not_silently_replaced(declared):
    with pytest.raises(UnicodeDecodeError):
        decode_public_html(b'\xff\x00\xda', declared)
