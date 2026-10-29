import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_cwh_inline_review import response_object
from cwh_remaining_research import query_values


def test_query_planning_uses_an_envelope_supported_by_actual_native_adapter():
    queries=['2026 行政法规 清理 专家','2026 法规修改 企业合规 难点',
             '2026 法规废止 权益保障 影响','2026 国常会 制度衔接 评论']
    wire=json.dumps({'type':'result','is_error':False,'result':
        json.dumps({'items':[{'query':q} for q in queries]},ensure_ascii=False)},ensure_ascii=False)
    parsed=response_object(wire)
    assert [r['query'] for r in parsed['items']]==queries
    assert not any('decision' in r or 'verdict' in r for r in parsed['items'])
    assert query_values(parsed)==queries


def test_actual_glm_numbered_query_slots_are_normalized_without_changing_words():
    output={'items':[{'query':'2026 法规清理 专家','query_2':'2026 条款衔接 分析',
                     'query_3':'2026 法律制度 改革','query_4':'2026 企业合规 评论'}]}
    assert query_values(output)==list(output['items'][0].values())


@pytest.mark.parametrize('output',[{'queries':['2026 x']},{'items':['2026 x']},
    {'items':[{'query':'2026 x','query_1':'2026 y'}]}, {'items':[{'query':'2026 x','reason':'x'}]}])
def test_unrecognized_or_ambiguous_slots_cannot_become_query_executions(output):
    assert query_values(output) is None
