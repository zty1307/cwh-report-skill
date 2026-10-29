import copy
import json
import sys
import time
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cwh_article_read_cache import key, load, store
from cwh_remaining_research import deadlines, effective_bundle
from run_cwh_resumable_pipeline import build_specs


def material(tmp_path):
    log=tmp_path/'native.jsonl';log.write_text('actual model output','utf-8')
    packet={'topic':'当前议题','period':{'start':'2026-10-16','end':'2026-10-20'},'agenda_topics':['当前议题']}
    item={'id':'w1','origin':'web','url':'https://example.org/a','content':'完整原文。',
          'title':'分析','source':'报纸','published_at':'2026-10-18','segment_scope':'p1','segment_scheme':'sentence_v2'}
    choice={'id':'w1','decision':'excluded','reason':'原文仅有会议事实','claims':[]}
    run={'session_id':'actual-native-run','log':str(log),'seconds':12}
    return packet,item,choice,run


def test_changed_batch_and_scoped_id_reuse_completed_reading_without_new_semantics(tmp_path):
    packet,item,choice,run=material(tmp_path)
    k=key(packet,item,'reading rules',['glm'])
    assert store(tmp_path/'cache',k,choice,run)
    moved={**item,'id':'w72','discovery_query_id':'q25','capture':{'captured_at':'later'}}
    assert key(packet,moved,'reading rules',['glm'])==k
    cached,receipt=load(tmp_path/'cache',k,moved['id'])
    assert cached=={**choice,'id':'w72'}
    assert receipt['session_id']==run['session_id'] and receipt['cache_reused'] and receipt['seconds']==0
    assert choice['id']=='w1'


@pytest.mark.parametrize('change',['text','model','prompt','topic','date','identity','segmentation'])
def test_different_semantic_task_is_not_mislabeled_completed(tmp_path,change):
    packet,item,choice,run=material(tmp_path);original=key(packet,item,'rules',['glm'])
    model=['glm'];prompt='rules'
    if change=='text':item['content']+='不能保证。'
    if change=='model':model=['other']
    if change=='prompt':prompt='new rules'
    if change=='topic':packet['topic']='另一个议题'
    if change=='date':packet['period']['end']='2026-10-21'
    if change=='identity':item['source']='另一家媒体'
    if change=='segmentation':item['segment_scheme']='other'
    assert key(packet,item,prompt,model)!=original


@pytest.mark.parametrize('tamper',['payload','log'])
def test_corrupted_cache_fails_instead_of_silently_rereading(tmp_path,tamper):
    packet,item,choice,run=material(tmp_path);k=key(packet,item,'r',['glm']);root=tmp_path/'c'
    store(root,k,choice,run)
    if tamper=='payload':
        path=root/(k+'.json');data=json.loads(path.read_text('utf-8'));data['payload']['choice']['claims']=['invented']
        path.write_text(json.dumps(data),'utf-8')
    else:Path(run['log']).write_text('changed','utf-8')
    with pytest.raises(ValueError):load(root,k,'w1')


def test_no_native_receipt_cannot_create_completed_cache(tmp_path):
    packet,item,choice,run=material(tmp_path)
    assert not store(tmp_path/'cache','key',choice,{'session_id':'claimed-only'})
    assert load(tmp_path/'cache','key','w1') is None


def test_optional_node_uses_current_clock_and_runs_after_all_primary_research():
    old=[s.stage_id for s in build_specs()];assert 'domestic_remaining_research' not in old
    specs=build_specs(True);ids=[s.stage_id for s in specs]
    assert ids.index('hotwords')<ids.index('domestic_remaining_research')<ids.index('render')
    assert 'domestic_remaining_research' in next(s for s in specs if s.stage_id=='render').dependencies
    contract={'research_deadline_seconds':2460};policy={'independent_review_reserve_seconds':240,'synthesis_reserve_seconds':180}
    assert deadlines(100,contract,policy)==(2125,2305,2545)


def test_unverified_supplement_cannot_replace_verified_fallback(tmp_path):
    artifacts=tmp_path/'artifacts';artifacts.mkdir();base=artifacts/'analysis_bundle_verified.json';base.write_text('{}')
    receipt=artifacts/'remaining_research_receipt.json'
    receipt.write_text(json.dumps({'promoted':False,'effective_bundle':str(artifacts/'bad.json')}))
    assert effective_bundle(tmp_path)==base
    receipt.write_text(json.dumps({'promoted':True,'effective_bundle':str(base),'effective_bundle_sha256':'wrong'}))
    with pytest.raises(ValueError):effective_bundle(tmp_path)


def test_host_origin_includes_launch_and_resume_waiting(tmp_path):
    from cwh_pipeline_runtime import PipelineRunner,StageSpec,StageOutcome
    origin=time.time()-50
    contract={'budget_origin_epoch':origin,'wall_clock_budget_seconds':2700}
    spec=StageSpec('one','one')
    runner=PipelineRunner(tmp_path,[spec],{'one':lambda r,s:StageOutcome.succeeded()},pipeline_name='clock',input_contract=contract)
    assert runner.state['budget_started_epoch']==origin
    assert 2648<runner.remaining_budget_seconds()<2651
    resumed=PipelineRunner(tmp_path,[spec],{'one':lambda r,s:StageOutcome.succeeded()},pipeline_name='clock',input_contract=contract)
    assert resumed.state['budget_started_epoch']==origin


def test_real_batch_reader_reuses_all_completed_articles_after_repartition(tmp_path,monkeypatch):
    import run_cwh_compiled_worker as worker
    packet,item,_,_=material(tmp_path)
    packet.update(delivery_policy='deliver_available_with_gaps',screen_integration_active=True,
        screened_readings=[],screen_reading_runs=[],_reading_cache_root=str(tmp_path/'cache'))
    packet['items']=[{**item,'id':f'w{i}','url':f'https://example.org/{i}'} for i in range(1,4)]
    calls=[]
    def native(packets,prompt,command,workspace,deadline,**kwargs):
        ids=[r['id'] for r in packets[0]['items']];calls.append(ids)
        log=tmp_path/f'call-{len(calls)}.jsonl';log.write_text(json.dumps(ids),'utf-8')
        return ([{'items':[{'id':i,'decision':'excluded','reason':'只陈述会议事实','claims':[]} for i in ids]}],
                {'session_id':f'run-{len(calls)}','log':str(log),'seconds':1})
    monkeypatch.setattr(worker,'author_topic_decisions',native)
    args=dict(reuse_cache=True,feedback=[],maximum_request_seconds=90)
    first=tmp_path/'first';first.mkdir()
    worker.review_author_article_batches(packet,[{'items':packet['items'][:2]},{'items':packet['items'][2:]}],
        'prompt',['glm'],first,time.monotonic()+300,**args)
    assert calls==[['w1','w2'],['w3']]
    second=tmp_path/'changed-batch';second.mkdir()
    result,run=worker.review_author_article_batches(packet,[{'items':list(reversed(packet['items']))}],
        'prompt',['glm'],second,time.monotonic()+300,**args)
    assert calls==[['w1','w2'],['w3']]  # zero additional model readings
    assert {r['id'] for r in result['items']}=={'w1','w2','w3'}
    assert all(r['status']=='completed_article_cache_reused' for r in run['batch_manifest'])
