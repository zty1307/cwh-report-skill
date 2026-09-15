import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_semantic_compiler import labeled_publication_date, exclude_certain_period_misses


@pytest.mark.parametrize('header', [
    '2026-01-07 16:46\n发布于：某省',
    '来源：某新闻客户端日期：2026-01-07 11:16:39',
])
def test_explicit_publication_headers_veto_outside_period_without_model_inference(header):
    content = '网站首页\n文章标题\n' + header + '\n会议发生在1月2日，某专家评论。'
    evidence = labeled_publication_date(content)
    assert evidence['date'] == '2026-01-07'
    assert content[evidence['start']:evidence['end']] == evidence['quote']
    packet = {'period': {'start': '2026-01-01', 'end': '2026-01-04'},
              'items': [{'id': 'w1', 'origin': 'web', 'content': content}]}
    decision = {'items': [{'id': 'w1', 'decision': 'eligible', 'published_at': '2026-01-02',
                           'date_quote': '1月2日', 'claims': [{'claim': '原模型观点'}]}]}
    frozen = copy.deepcopy((packet, decision))
    result = exclude_certain_period_misses(packet, decision)
    assert result['items'][0]['decision'] == 'excluded'
    assert result['items'][0]['claims'] == []
    assert result['items'][0]['transport_exclusions'][0]['original_review'] == decision['items'][0]
    assert (packet, decision) == frozen


@pytest.mark.parametrize('content', [
    '2026年1月7日 IT频道最新文章\n文章正文',
    '正文提到来源：某机构，会议日期：2026-01-07，随后作出判断。',
    '01-07 16:46\n发布于：某省',
    '2026-01-07 16:46\n正文提及某个事件发生时间',
    '发布日期：2026-01-02\n来源：新闻日期：2026-01-07',
])
def test_navigation_event_missing_year_unlabeled_or_conflicting_dates_are_not_inferred(content):
    assert labeled_publication_date(content) is None
