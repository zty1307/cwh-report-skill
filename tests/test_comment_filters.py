import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_comment_filters import is_procedural_only


def test_exact_operation_noise_is_fixed_but_actual_attitudes_are_not_guessed():
    assert is_procedural_only('转发了') and is_procedural_only(' 已转发！ ')
    assert not is_procedural_only('转发了，支持这项政策')
    assert not is_procedural_only('关注公共服务配套细则')
    assert not is_procedural_only('点赞这项惠民政策')
