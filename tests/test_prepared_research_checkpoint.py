import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cwh_prepared_research import save,load,collection_key
from cwh_adaptive_web_research import plan_targeted_queries


def test_completed_collection_preserves_all_originals_and_is_not_semantic_approval(tmp_path):
    path=tmp_path/'prepared.json';packets=[{'topic':'A','items':[{'id':'w1','content':'完整原文，不能被剩余预算擦掉。'}]}]
    before=copy.deepcopy(packets);save(path,'immutable-key',packets,[{'topic':'A'}],[{'topic':'A','queries':[]}])
    packets[0]['items']=[]
    assert load(path,'immutable-key')['packets']==before
    assert 'no final claim' in json.loads(path.read_text('utf-8'))['scope']
    with pytest.raises(ValueError):save(path,'immutable-key',[],[],[])
    with pytest.raises(ValueError):load(path,'different-source')


def test_modified_frozen_payload_is_rejected_instead_of_silently_refetching(tmp_path):
    path=tmp_path/'prepared.json';save(path,'same',[],[],[])
    row=json.loads(path.read_text('utf-8'));row['payload']['observed']=[{'forged':'changed'}]
    path.write_text(json.dumps(row),encoding='utf-8')
    with pytest.raises(ValueError):load(path,'same')


def test_successful_native_query_plan_remains_identical_when_retry_time_is_short(tmp_path):
    needs={'A':{'shortfall':3,'raw_nominated_subjects':3}};plan={'monitoring_period':{'start':'2026-10-16','end':'2026-10-20'},'topics':[{'topic':'A','search_subject':'当前政策A'}]}
    calls=[]
    def native(*a,**k):
        calls.append(True)
        return {'topics':[{'topic':'A','queries':[f'2026 当前政策A 专家角度{n}' for n in range(4)]}]},{'session_id':'real-plan'}
    original=plan_targeted_queries(needs,plan,[],tmp_path,45,native)
    def no_call(*a,**k):pytest.fail('A completed query plan must be reused before the deadline guard')
    again=plan_targeted_queries(needs,plan,[],tmp_path,0,no_call)
    assert again==original and len(calls)==1
    assert json.loads((tmp_path/'targeted_query_plan.json').read_text('utf-8'))['error'] is None


def test_changed_query_plan_payload_is_not_accepted_as_a_new_fallback(tmp_path):
    needs={'A':{'shortfall':1}};plan={'monitoring_period':{'start':'2026-10-16','end':'2026-10-20'},'topics':[{'topic':'A','search_subject':'当前政策A'}]}
    plan_targeted_queries(needs,plan,[],tmp_path,0,lambda *a:pytest.fail('No new native call'))
    path=tmp_path/'targeted_query_plan.json';row=json.loads(path.read_text('utf-8'));row['queries']['A'][0]='changed'
    path.write_text(json.dumps(row),encoding='utf-8')
    with pytest.raises(ValueError):plan_targeted_queries(needs,plan,[],tmp_path,45,lambda *a:pytest.fail('No new native call'))


def test_two_local_repairs_keep_original_unread_markers_and_real_run_ids():
    from cwh_prepared_research import carry_repair_runs
    from run_cwh_compiled_worker import actual_author_run_ids
    initial={'transport':'sequential_single_topic_semantic','topic_runs':[
        {'session_id':'original-native','article_reading_deferrals':[{'id':'w2','kind':'invalid_model_response'}]}], 'seconds':10}
    before=copy.deepcopy(initial)
    edited=carry_repair_runs(initial,{'session_id':'local-edit-1','seconds':3})
    edited=carry_repair_runs(edited,{'session_id':'local-edit-2','seconds':4})
    assert edited['topic_runs'][0]['article_reading_deferrals']==before['topic_runs'][0]['article_reading_deferrals']
    assert actual_author_run_ids(edited)==['original-native','local-edit-1','local-edit-2']
    assert edited['seconds']==17 and initial==before
