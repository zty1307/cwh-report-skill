import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from raw_system_workbook_pipeline import build_overseas_review_packet


def test_overseas_focus_rules_distinguish_policy_focus_and_incidental_catalysts():
    packet = build_overseas_review_packet([], {}, {'meeting_title': '本期会议', 'topic_titles': ['本期决策']}, [])
    rules = '\n'.join(packet['instructions'])
    assert '全文主线判断' in rules
    assert '催化因素、背景注脚或孤立要闻' in rules
    assert '不得按财经题材或合集标题一概排除' in rules
    assert 'review_reason须说明全文主线' in rules
    assert '7月31日' not in rules and '核电' not in rules
