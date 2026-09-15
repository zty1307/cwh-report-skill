"""Reading-contract tests do not certify model semantic decisions."""
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from raw_system_workbook_pipeline import build_overseas_review_packet, filter_public_top


def test_overseas_contract_preserves_bodies_and_requires_current_decision_link():
    rows = [{'source_row': 1, 'source': '示例外媒', 'url': 'https://example.test/a',
             'title': '某地活动', 'content': '活动报道。国务院常务会议作为背景。'}]
    original = copy.deepcopy(rows)
    packet = build_overseas_review_packet(rows, {}, {'topic_titles': ['当前议题']}, [])
    assert rows == original
    assert packet['items'][0]['content'] == original[0]['content']
    assert any('本次会议的具体决策' in rule and '一般领导人活动' in rule for rule in packet['instructions'])
    assert any('导航、登录提示' in rule and '推荐列表' in rule for rule in packet['instructions'])


def test_public_top_contract_distinguishes_whole_article_from_one_chapter():
    row = {'source_row': 1, 'account': '示例账号', 'url': 'https://example.test/b',
           'title': '综合时事', 'content': '外事新闻。国常会部署当前议题。其他事件。', 'read_count': 100}
    original = copy.deepcopy(row)
    result = filter_public_top([row], {'meeting_anchor_patterns': ['国常会'], 'public_top_n': 10,
                                     'public_roundup_patterns': []},
                               {'topic_titles': ['当前议题'], 'topic_aliases': [['当前议题']]})
    assert row == original
    packet = result['review_packet']
    assert packet['items'][0]['content'] == original['content']
    assert any('一个独立章节' in rule and '整篇主体' in rule for rule in packet['instructions'])
