import copy,json,sys,time
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cwh_feedback_recall import rank_reserves,rejection_feedback,query_is_new
from cwh_raw_recall_collection import collect_subset


def test_long_weekly_with_local_practical_advice_outranks_short_communique_and_skips_read_sources():
    topic='审议通过《国务院关于修改和废止部分行政法规的决定（草案）》'
    rows=[{'id':'long','content':'其他领域报道。'*1300+'行政法规清理后，建议企业及时更新内部制度引用依据，防止沿用旧条文。'},
          {'id':'short','content':'会议决定修改行政法规，要求加强风险研判，保障权益，完善机制。'},
          {'id':'already','content':'行政法规清理后，应对照清单更新合规台账，防止遗漏。'}]
    rows.append({'id':'mirror','content':rows[-1]['content']})
    hints=[{'id':r['id'],'decision':'reserve','topics':topic} for r in rows]
    selected,audit=rank_reserves(rows,hints,topic,[],[rows[2]],limit=2)
    assert [r['id'] for r in selected]==['long','short']
    assert selected[0]['content']==rows[0]['content'] and len(selected[0]['content'])>5000
    assert audit['unread_candidates']==2


def test_feedback_carries_actual_reasons_and_separates_unread_material():
    packet={'items':[{'id':f'w{i}','origin':'web','title':'原题','url':f'https://a/{i}','content':'完整正文'} for i in range(3)]}
    packet['items'][2]['content']=''
    choices={'w0':{'decision':'excluded','reason':'实际讨论2024年既有条例，非本次修改'},
             'w1':{'decision':'excluded','reason':'本批尚未完成阅读'}}
    feedback=rejection_feedback(packet,choices,deferred_ids=['w1'])
    assert [r['id'] for r in feedback['completed_rejections']]==['w0']
    assert feedback['completed_rejections'][0]['reason']==choices['w0']['reason']
    assert {r['id'] for r in feedback['pending_not_negative']}=={'w1','w2'}


def test_formatted_old_query_is_not_new_discovery():
    assert not query_is_new('2026  “法规清理”  律师',['2026 "法规清理" 律师'])
    assert query_is_new('2026 10月 行政法规 台账 建议',['2026 行政法规 专家 解读'])


def test_raw_collection_reuses_native_success_after_local_conversion_interruption(tmp_path,monkeypatch):
    import cwh_raw_recall_collection as module
    row={'id':'r2','title':'法规评论','content':'完整原文','account':'原账号','published_at':'2026-10-18'}
    agenda=tmp_path/'agenda.json';agenda.write_text(json.dumps({'topics':['当前议题']}),'utf-8')
    calls=[]
    def native(command,**kwargs):
        calls.append(command);out=tmp_path/'rc/job';(out/'model').mkdir(parents=True);(out/'results_guarded').mkdir()
        module.atomic_write_json(out.with_suffix('.native_launch.json'),{'run_requested':True,'requested_model':'glm'})
        module.atomic_write_json(out/'model/sources.json',[row])
        module.atomic_write_json(out/'model/article_decisions.json',[{'id':'r2'}])
        module.atomic_write_json(out/'results_guarded/candidates_pending_independent_review.json',[])
        return 0
    monkeypatch.setattr(module,'run_scoped_command',native)
    monkeypatch.setattr(module,'materialize_screen',lambda *args:({'当前议题':[]},[],[]))
    args=(tmp_path/'rc',[row],{'r2':row},agenda,'glm',time.time()+200)
    first=collect_subset(*args);assert len(calls)==1 and first[3]['completed_ids']==['r2']
    # Native success is durable even if local code stopped before recording it.
    (tmp_path/'rc/completed_collection.json').unlink()
    second=collect_subset(*args);assert len(calls)==1 and second[3]['reused_completed_collection']
    assert collect_subset(*args)[3]['reused_completed_collection'] and len(calls)==1
    changed=copy.deepcopy(row);changed['content']+='变化'
    with pytest.raises(ValueError):collect_subset(tmp_path/'rc',[changed],{'r2':changed},agenda,'glm',time.time()+200)


def test_explicit_old_publication_bypasses_native_reading_without_claiming_semantic_completion(tmp_path):
    from run_cwh_compiled_worker import author_transport_with_fixed_unread_web,author_topic_decisions
    from cwh_article_read_cache import store
    packet={'topic':'当前议题','period':{'start':'2026-10-16','end':'2026-10-20'},'items':[
        {'id':'w1','origin':'web','url':'https://a/1','title':'旧解读','content':'发布时间：2024年10月10日\n原文。'}]}
    transport,fixed=author_transport_with_fixed_unread_web(packet)
    assert not transport['items'] and fixed['w1']['classification_origin']=='deterministic_publication_period_gate'
    decisions,run=author_topic_decisions([packet],'rules',['must-not-run'],tmp_path/'ws',time.monotonic()+100,
        reading_only=True,allow_article_batches=False,reuse_cache=True)
    assert run['topic_runs'][0]['model_invoked'] is False
    assert not store(tmp_path/'cache','key',fixed['w1'],{'log':'unused'})


def test_event_date_in_body_does_not_skip_publication_review():
    from run_cwh_compiled_worker import author_transport_with_fixed_unread_web
    packet={'topic':'当前议题','period':{'start':'2026-10-16','end':'2026-10-20'},'items':[
        {'id':'w1','origin':'web','content':'本文分析2024年10月10日发生的背景事件，并评论本期措施。'}]}
    model,fixed=author_transport_with_fixed_unread_web(packet)
    assert not fixed and model['items'][0]['id']=='w1'


def test_supplement_selection_receives_verified_baseline_without_full_article_repeat():
    from cwh_claim_synthesis import flat_packet
    baseline=[{'formal_claim':'原来已核验的机制判断','speaker_name':'原主体'}]
    packet,_=flat_packet({'topic':'当前政策','eligible_items':[],
        'previously_excluded_items':[],'previously_verified_claims':baseline})
    assert packet['previously_verified_claims']==baseline
