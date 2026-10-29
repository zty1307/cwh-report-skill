import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from cwh_adaptive_web_research import raw_topic_needs, screen_allowance, topic_slice, plan_targeted_queries, reading_order
from cwh_host_research import topic_search_tasks, HostModelError
from cwh_model_contract import execution_profile, resolved_stage_budgets
from run_cwh_compiled_worker import balanced_fetch_urls


def test_45m_keeps_review_delivery_and_protected_web_time_inside_whole_clock():
    name, p = execution_profile('bounded_45m')
    assert name == 'bounded_45m' and p['wall_clock_budget_seconds'] == 2700
    assert p['research_deadline_seconds'] == 2460
    for mode in ('raw_workbook', 'standard_workbook'):
        b = resolved_stage_budgets(p, mode)
        assert sum(b.values())+p['reserved_delivery_buffer_seconds'] <= 2700
        if mode == 'raw_workbook':
            assert sum(b.values())+p['reserved_delivery_buffer_seconds'] == 2700
        assert (b['domestic_evidence_verification'],b['render'],b['delivery_gate']) == (300,135,100)
    for remaining in (200,500,700,900,1200):
        allowance = screen_allowance(remaining, 4, 150)
        assert allowance <= 360 and allowance >= 0
        assert remaining-allowance >= min(remaining,600)


def test_raw_gap_counts_distinct_nominated_subjects_not_number_of_claims():
    screen = {'topics': {'empty': [], 'thin': [{'decision': {'claims': [
        {'speaker':'甲','role':'教授'}, {'speaker':'甲','role':'教授'}]}}],
        'enough':[{'decision':{'claims':[{'speaker':str(n),'role':'教授'} for n in range(6)]}}]}}
    needs = raw_topic_needs(screen,list(screen['topics']),6)
    assert [needs[t]['priority_weight'] for t in screen['topics']] == [3,2,1]
    assert needs['thin']['raw_nominated_subjects'] == 1


def test_weak_topic_share_increases_without_borrowing_remaining_topics_floor():
    assert topic_slice(600,[3,1,1,1]) > topic_slice(600,[1,1,1,1])
    assert 75 <= topic_slice(600,[3,1,1,1]) <= 600-75*3
    assert 0 < topic_slice(100,[3,1,1,1]) <= 100-25*3


def planner_fixture():
    needs = {'议题A':{'shortfall':2,'raw_nominated_subjects':4}}
    plan = {'monitoring_period':{'start':'2026-10-16','end':'2026-10-20'},
            'topics':[{'topic':'议题A','search_subject':'议题A'}]}
    return needs,plan


def test_native_targeted_planning_is_separate_from_actual_search_and_approval(tmp_path):
    needs,plan=planner_fixture();calls=[]
    def native(packet,prompt,command,workspace,label,timeout,**kwargs):
        calls.append((packet,label,timeout))
        return {'topics':[{'topic':'议题A','queries':[f'2026 议题A 解读{n}' for n in range(4)]}]},{'session_id':'native-query-planner'}
    result=plan_targeted_queries(needs,plan,[],tmp_path,45,native)
    assert len(result['议题A'])==4 and calls[0][1]=='shortfall-query-plan'
    assert (tmp_path/'targeted_query_plan.json').exists()


def test_bad_query_year_falls_back_without_inventing_a_search(tmp_path):
    needs,plan=planner_fixture()
    def native(*args,**kwargs):
        return {'topics':[{'topic':'议题A','queries':[f'2025 议题A {n}' for n in range(4)]}]},{'session_id':'bad-year'}
    result=plan_targeted_queries(needs,plan,[],tmp_path,45,native)
    assert all('2026' in q for q in result['议题A'])


def test_permission_error_is_not_relabelled_as_empty_research(tmp_path):
    needs,plan=planner_fixture()
    def deny(*a,**k): raise HostModelError('permission denied',23,category='permission_denied')
    with pytest.raises(HostModelError):plan_targeted_queries(needs,plan,[],tmp_path,45,deny)


def test_targeted_queries_reach_observed_transport_not_just_the_plan():
    plan={'topic':'议题A','stable_source_tasks':[{'source_id':str(n),'query':f'2026 base{n}','must_check':True} for n in range(6)],
          'queries':{'academic_and_think_tank_viewpoints':['2026 academic1','2026 academic2']},
          'targeted_shortfall_queries':[f'2026 targeted{n}' for n in range(4)],'query_execution_limit':14}
    tasks=topic_search_tasks(plan,{'start':'2026-10-16'})
    assert len(tasks)==14 and sum(bool(t.get('targeted_shortfall')) for t in tasks)==4
    assert all(t['route']=='open_web' for t in tasks[-4:])


def test_targeted_current_pages_are_queued_before_portals_and_old_pages():
    obs={'queries':[{'route':'stable_registry','results':[{'url':'https://a.test/','title':'首页'}]},
        {'route':'open_web','targeted_shortfall':True,'results':[
            {'url':'https://a.test/20250101/article.html','title':'议题A 专家解读'},
            {'url':'https://b.test/20261017/article.html','title':'议题A 分析'}]}]}
    before=copy.deepcopy(obs);ordered=reading_order(obs,{'start':'2026-10-16','end':'2026-10-20'})
    assert balanced_fetch_urls(ordered,1,topic='议题A')==['https://b.test/20261017/article.html']
    assert obs==before


def test_allocated_query_completion_is_not_reported_as_14_query_exhaustion():
    from test_search_budget import material
    from cwh_available_delivery import prepare_available_delivery
    from cwh_search_budget import valid_query_budget_stop, query_budget_evidence
    bundle=material();research=bundle['research_audit']['domestic_media_research']
    research['execution_profile']='bounded_45m'
    research['candidate_pool_by_topic'][0]['saturation']['allocated_query_limit']=10
    result=prepare_available_delivery(bundle)
    saturation=result['research_audit']['domestic_media_research']['candidate_pool_by_topic'][0]['saturation']
    assert valid_query_budget_stop(saturation,'bounded_45m')
    assert saturation['budget_stop']['saturation_proven'] is False
    assert saturation['budget_stop']['allocated_query_limit']==10
    assert '分配的10次查询（配置上限26次）' in result['metadata']['research_budget_gaps'][0]
    saturation['allocated_query_limit']=3
    assert query_budget_evidence(saturation,'bounded_45m') is None


def test_author_wiring_prioritizes_thin_topic_and_passes_extra_queries_to_real_collector(tmp_path,monkeypatch):
    import json,time
    import run_cwh_compiled_worker as worker
    import cwh_screen_bridge as bridge
    import cwh_reading_priority as priority
    _,policy=execution_profile('bounded_45m')
    topics=['原始充分','原始空缺'];plans=[]
    for topic in topics:
        plans.append({'topic':topic,'search_subject':topic,'query_execution_limit':14,
            'stable_source_tasks':[{'source_id':str(n),'query':f'2026 {topic} base{n}','must_check':True} for n in range(6)],
            'queries':{'academic_and_think_tank_viewpoints':[f'2026 {topic} academic1',f'2026 {topic} academic2']}})
    plan={'topics':plans,'monitoring_period':{'start':'2026-10-16','end':'2026-10-20'},
          'execution_profile':'bounded_45m','execution_budget':{'initial_public_page_fetches_per_topic':12,
              'max_full_page_fetches_per_topic':18}}
    import hashlib
    corpus=tmp_path/'public_article_evidence.json';corpus.write_text('真实原始语料固定内容',encoding='utf-8')
    index={'topics':[{'topic':t} for t in topics],'candidate_count':1,
           'source_sha256':hashlib.sha256(corpus.read_bytes()).hexdigest()}
    files={'research_plan':plan,'public_corpus_index':index,'source_registry':{'version':'test'},
           'execution_policy':{'profiles':{'bounded_45m':policy}}};inputs={}
    for name,value in files.items():
        path=tmp_path/f'{name}.json';path.write_text(json.dumps(value),encoding='utf-8');inputs[name]=str(path)
    screen={'topics':{'原始空缺':[],'原始充分':[{'record':{},'decision':{'claims':[
        {'speaker':str(n),'role':'教授'} for n in range(6)]}}]},'runs':[]}
    monkeypatch.setattr(bridge,'prepare_screen',lambda *a,**k:screen)
    monkeypatch.setattr(bridge,'packet_readings',lambda *a:[])
    monkeypatch.setattr(worker,'semantic_json',lambda *a,**k: (
        {'topics':[{'topic':'原始空缺','queries':[f'2026 原始空缺 targeted{n}' for n in range(4)]}]},
        {'session_id':'native-planner'}))
    observed=[]
    def collect(topic_plan,period,command,workspace,timeout):
        tasks=topic_search_tasks(topic_plan,period);observed.append((topic_plan['topic'],len(tasks)))
        return {'topic':topic_plan['topic'],'queries':[{**t,'results':[],'query_id':str(n)} for n,t in enumerate(tasks)]}
    monkeypatch.setattr(worker,'collect_topic',collect)
    monkeypatch.setattr(worker,'cached_public_pages',lambda *a,**k:[])
    monkeypatch.setattr(worker,'recover_failed_page_slots',lambda ws,obs,urls,pages,*a,**k:pages)
    monkeypatch.setattr(priority,'prioritize_pages',lambda obs,topic,limit,fallback,*a,**k:fallback)
    monkeypatch.setattr(worker,'make_packet',lambda topic,period,*a:{'topic':topic,'period':period,'items':[]})
    class StopBeforeNativeReading(Exception):pass
    def inspect(packets,*a,**k):
        assert [p['topic'] for p in packets]==['原始空缺','原始充分']
        assert [p['protected_web_policy']['priority_weight'] for p in packets]==[3,1]
        assert all(p['screen_integration_active'] for p in packets)
        raise StopBeforeNativeReading
    monkeypatch.setattr(worker,'author_topic_decisions',inspect)
    monkeypatch.setenv('CWH_SEMANTIC_COMMAND_JSON','[]');monkeypatch.setenv('CWH_SEARCH_COMMAND_JSON','[]')
    with pytest.raises(StopBeforeNativeReading):
        worker.author({'inputs':inputs,'execution_profile':'bounded_45m','stage_workspace':str(tmp_path)},time.monotonic()+1200)
    assert observed==[('原始空缺',14),('原始充分',10)]
    # A late retry must not plan/search/fetch again or shrink the source pool.
    monkeypatch.setattr(bridge,'prepare_screen',lambda *a,**k:pytest.fail('Raw screen was already completed'))
    monkeypatch.setattr(worker,'collect_topic',lambda *a,**k:pytest.fail('Completed search must be frozen'))
    monkeypatch.setattr(worker,'cached_public_pages',lambda *a,**k:pytest.fail('Completed source acquisition must be frozen'))
    monkeypatch.setattr(worker,'semantic_json',lambda *a,**k:pytest.fail('Query plan must not be regenerated'))
    inputs['validation_problems']=['仅修已有观点的原文定位']
    with pytest.raises(StopBeforeNativeReading):
        worker.author({'inputs':inputs,'execution_profile':'bounded_45m','stage_workspace':str(tmp_path)},time.monotonic()+1)


def test_weak_first_compilation_returns_to_agenda_order_before_strict_merge():
    from cwh_adaptive_web_research import agenda_order
    from run_cwh_batched_viewpoints import merge_topic_bundles
    def part(topic,claim):
        return {'viewpoints':{'by_topic':[{'topic':topic,'clusters':[{'evidence':[{'formal_claim':claim}]}]}]},
            'research_audit':{'domestic_media_research':{'registry_version':'test','execution_profile':'bounded_45m',
              'open_search_completed':True,'required_source_ids':[],
              'coverage_by_topic':[{'topic':topic,'checks':[]}],
              'candidate_pool_by_topic':[{'topic':topic,'candidates':[]}],
              'public_article_corpus_review':{'topic_reviews':[{'topic':topic}]}}}}
    parts=[part('末议题','完整原观点甲'),part('首议题','完整原观点乙')];before=copy.deepcopy(parts)
    merged=merge_topic_bundles(agenda_order(parts,['首议题','末议题']),['首议题','末议题'],0,'actual-native')
    assert [t['topic'] for t in merged['viewpoints']['by_topic']]==['首议题','末议题']
    assert parts==before
    with pytest.raises(ValueError):agenda_order([parts[0],parts[0]],['首议题','末议题'])
