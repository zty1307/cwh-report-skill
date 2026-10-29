import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import cwh_host_research as host


def collect(tmp_path, monkeypatch, planned, actuals):
    monkeypatch.setattr(host,'topic_search_tasks',lambda *a:[
        {'source_id':'open_web','route':'open_web','query':q} for q in planned])
    events=[]
    for n,query in enumerate(actuals):
        events.append({'message':{'content':[{'type':'tool_use','id':f't{n}',
            'name':'WebSearch','input':{'query':query}}]}})
        events.append({'message':{'content':[{'type':'tool_result','tool_use_id':f't{n}',
            'content':f'## 1. [actual source{n}](https://example.test/article{n})\nactual snippet'}]}})
    text='\n'.join(json.dumps(e,ensure_ascii=False) for e in events)
    def invoke(*a):
        path=tmp_path/'actual-tool-log.jsonl';path.write_text(text,encoding='utf-8')
        return text,{'session_id':'native-search','started_at':'2026-10-22T03:00:00+00:00',
            'completed_at':'2026-10-22T03:00:10+00:00','log':str(path),'exit_code':0}
    monkeypatch.setattr(host,'invoke',invoke)
    return host.collect_topic({'topic':'current'}, {'start':'2026-10-16'}, [],tmp_path,60)


def test_restore_observed_results_preserving_actual_query_and_original_plan(tmp_path,monkeypatch):
    planned='2026 ("“人工智能+”" OR "算电协同") 专家 解读'
    actual='2026 (“人工智能+” OR “算电协同”) 专家 解读'
    result=collect(tmp_path,monkeypatch,[planned],[actual])
    row=result['queries'][0]
    assert row['status']=='completed' and row['query']==actual
    assert row['planned_query']==planned and row['result_urls']==['https://example.test/article0']
    assert result['all_queries_observed'] is True
    saved=json.loads((tmp_path/'research_observations.json').read_text('utf-8'))
    assert saved==result and actual in (tmp_path/'actual-tool-log.jsonl').read_text('utf-8')


@pytest.mark.parametrize('actual',[
    '2025 (人工智能+ OR 算电协同) 专家 解读',
    '2026 (人工智能+ AND 算电协同) 专家 解读',
    '2026 (人工智能+ OR 数据市场) 专家 解读',
    '2026 (人工智能+ OR 算电协同) 专家 解读 新增条件'])
def test_changed_year_operator_terms_or_extra_scope_stay_unmatched(tmp_path,monkeypatch,actual):
    result=collect(tmp_path,monkeypatch,['2026 ("人工智能+" OR "算电协同") 专家 解读'],[actual])
    assert result['queries'][0]['status']=='access_failed'
    assert result['queries'][0]['results']==[] and result['all_queries_observed'] is False


def test_ambiguous_variants_are_not_arbitrarily_picked(tmp_path,monkeypatch):
    result=collect(tmp_path,monkeypatch,['2026 "教师法" 解读'],
                   ['2026 “教师法” 解读','2026 教师法 解读'])
    assert result['queries'][0]['status']=='access_failed'


def test_one_real_tool_execution_cannot_complete_two_planned_slots(tmp_path,monkeypatch):
    result=collect(tmp_path,monkeypatch,['2026 "教师法" 解读','2026 “教师法” 解读'],
                   ['2026 教师法 解读'])
    assert sum(q['status']=='completed' for q in result['queries'])==1
    assert result['all_queries_observed'] is False
