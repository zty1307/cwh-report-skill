"""Optimized independent screening entry; scripts+portable JSON model hosts.

This is not the full-report pipeline. Original experiment folders are immutable.
"""
import argparse,json,sys,time
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
from portable_screen import load,save,digest,prepare,run
from refined_filter import refine
from conservative_filter import csv_write
from opinion_gate_v8 import select,VERSION
from benchmark_recall_periods import prepare_review,ingest_review,bounded_call,HERE
from recover_identity_whitespace import recover

FILES=['run_optimized_screen.py','opinion_gate_v8.py','opinion_gate.py','recall_v8_policy.py','portable_screen.py',
       'refined_filter.py','conservative_filter.py','recover_more_views.py','benchmark_recall_periods.py',
       'recover_identity_whitespace.py','codex_json_transport.py','native_json_syntax.py','localize_native_decode.py','review_policy_versions.py']

def signature():
    result={n:digest((HERE/n).read_text(encoding='utf-8'))for n in FILES}
    normalizer=HERE/'prepare_records.py'
    if not normalizer.exists():normalizer=HERE.parent/'cwh_strict_screen/prepare_records.py'
    result['prepare_records.py']=digest(normalizer.read_text(encoding='utf-8'))
    return result

def schema_packets(review):
    schema=load(review/'response_schema.json');manifest=load(review/'manifest.json')
    for name in manifest['task_hashes']:
        task=load(review/'tasks'/name);task['output_schema']=schema
        save(review/'tasks'/name,task);manifest['task_hashes'][name]=digest(task)
    save(review/'manifest.json',manifest)

def complete_pool(review,out):
    sources={r['id']:r for r in load(review/'sources.json')};views=load(review/'reviewed_candidates.json')
    reviewed_ids={v['candidate_id']for v in views}
    unread=[{**v,'independent_decision':'unreviewed','independent_reason':'复核尚未完成','formal_ready':False}
            for v in load(review/'candidates.json')if v['candidate_id']not in reviewed_ids]
    recovered=[];all_views=[]
    for v in views:
        repaired=recover(sources[v['id']],v)
        if repaired:recovered.append(repaired)
        all_views.append(repaired or v)
    kept=[v for v in all_views if v['independent_decision']=='retain'and not v['errors']and v.get('report_sentence')]
    pending=[v for v in all_views if v['independent_decision']!='exclude'and v not in kept]+unread
    excluded=[v for v in all_views if v['independent_decision']=='exclude']
    save(out/'source_check_candidates.json',kept);save(out/'pending_candidates.json',pending)
    save(out/'excluded_candidates.json',excluded);save(out/'whitespace_recoveries.json',recovered)
    topics=load(review/'agenda.json')['topics'];lines=['待溯源候选，未核原始网页、身份及原发时间；不是正式可引用清单。',
        '保留不同实质判断及尚未语义去重的记录；脚本未把未读备用当作无用。','']
    for t in topics:
        vals=[v for v in kept if v['topic']==t];lines.extend([f'{t}（{len(vals)}条）',''])
        for v in vals:
            r=sources[v['id']];lines.extend([v['report_sentence'],f"编号：{v['candidate_id']}；监测时间：{r.get('published_at','')}",
                f"来源标题：{r['title']}",f"监测链接：{r.get('url','')}",''])
        if not vals:lines.extend(['本轮未取得通过的待溯源候选。',''])
    (out/'分议题待溯源候选.txt').write_text('\n'.join(lines),encoding='utf-8')
    return {'source_check_claims':len(kept),'speaker_topic_pairs':len({(v['topic'],v['kind'],v['name'])for v in kept}),
            'distinct_source_articles':len({v['id']for v in kept}),'pending_identity_or_rewrite':len(pending)-len(unread),
            'pending_unreviewed':len(unread),'pending_total':len(pending),
            'excluded_claims':len(excluded),'whitespace_recovered':len(recovered),
            'claims_by_topic':{t:sum(v['topic']==t for v in kept)for t in topics},'formal_ready':0}

def main():
    p=argparse.ArgumentParser();source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--workbook',type=Path);source.add_argument('--records',type=Path)
    p.add_argument('--agenda',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--frozen-rules',type=Path,required=True);p.add_argument('--budget-seconds',type=int,default=480)
    p.add_argument('--max-body-chars',type=int,default=450000);p.add_argument('--max-articles',type=int,default=99)
    p.add_argument('--exploration-slots',type=int,default=12);p.add_argument('--model',default='gpt-6.1-sol')
    p.add_argument('--command-json');p.add_argument('--review-command-json');p.add_argument('--run',action='store_true');a=p.parse_args()
    if signature()!=load(a.frozen_rules):raise ValueError('Changed frozen rules; use a new experiment specification')
    out=a.out.resolve()
    if out.exists():raise ValueError('Fresh job directory required')
    out.mkdir(parents=True);begin=time.monotonic();deadline=begin+a.budget_seconds
    state={'status':'preparing','policy':VERSION,'started_at':datetime.now(timezone.utc).isoformat(),'calls':[],
        'model_key':a.model if not a.command_json else 'custom_json_host','frozen_rules_hash':digest(load(a.frozen_rules)),
        'budget_seconds':a.budget_seconds,'cache_reuse':False,'formal_ready':0,
        'scope':'Raw workbook/normalized input -> scripted complete-article queue -> independent review of all nominations; excludes original-web verification and report writing.',
        'includes_excel_normalization':bool(a.workbook)}
    save(out/'benchmark.json',state)
    if a.workbook:
        norm=HERE/'prepare_records.py'
        if not norm.exists():norm=HERE.parent/'cwh_strict_screen/prepare_records.py'
        timing=bounded_call([sys.executable,str(norm),'--workbook',str(a.workbook.resolve()),'--out',str(out/'records.json')],None,out/'normalization.stdout.json',deadline)
        state['calls'].append({'stage':'normalization',**timing})
        if timing['exit_code']:raise RuntimeError('Normalization failed; see saved logs')
        records=load(out/'records.json')
    else:records=load(a.records);save(out/'records.json',records)
    start=time.monotonic();agenda=load(a.agenda);remaining,base_audit,base_summary=refine(records,agenda)
    chosen,audit,selection,index=select(remaining,agenda,a.max_articles,a.max_body_chars,a.exploration_slots)
    save(out/'filter/base_summary.json',base_summary);csv_write(out/'filter/base_audit.csv',base_audit)
    save(out/'filter/summary.json',selection);save(out/'filter/evidence_and_quote_aliases.json',index)
    csv_write(out/'filter/priority_audit.csv',audit);save(out/'filter/remaining_records.json',remaining)
    task_info=prepare(chosen,agenda,out/'model',90000,state['model_key'],mode='recall_v8')
    state.update(input_rows=len(records),base_remaining=len(remaining),selected_articles=len(chosen),
        selected_body_characters=sum(len(r['content'])for r in chosen),script_seconds=round(time.monotonic()-start,3),
        first_batches=task_info['batches'],status='waiting_first_model')
    save(out/'benchmark.json',state);print(json.dumps({'stage':'script','summary':selection},ensure_ascii=False),flush=True)
    if a.run:
        default=[sys.executable,str(HERE/'codex_json_transport.py'),'--model',a.model]
        read_command=json.loads(a.command_json)if a.command_json else default
        review_command=json.loads(a.review_command_json)if a.review_command_json else read_command
        for cmd in [read_command,review_command]:
            if not isinstance(cmd,list)or not cmd or not all(isinstance(s,str)for s in cmd):raise ValueError('Model host command must be a nonempty argv array')
        start=time.monotonic();state['reading']=run(out/'model',read_command,max(0,min(300,deadline-time.monotonic()-100)))
        state['reading_wall_seconds']=round(time.monotonic()-start,3)
        save(out/'benchmark.json',state);print(json.dumps({'stage':'reading','summary':state['reading']},ensure_ascii=False),flush=True)
        state['review_plan']=prepare_review(out/'model',out/'review');schema_packets(out/'review');ingest_review(out/'review')
        for task in sorted((out/'review/tasks').glob('*.json')):
            if time.monotonic()>=deadline:break
            timing=bounded_call(review_command,load(task),out/(task.stem+'.stdout.json'),deadline)
            state['calls'].append({'stage':task.stem,**timing});save(out/'benchmark.json',state)
            print(json.dumps(state['calls'][-1]),flush=True)
            if timing['exit_code']:break
            try:save(out/'review/responses'/task.name,load(out/(task.stem+'.stdout.json')))
            except (ValueError,OSError):break
        state['review']=ingest_review(out/'review');state['candidate_pool']=complete_pool(out/'review',out/'results')
        state['complete_selected_scope']=not state['reading']['unread_ids']and not state['reading']['invalid_responses']and not state['review']['unreviewed']and not state['review']['invalid_responses']
        state['status']='completed_selected_scope_pending_source_verification'if state['complete_selected_scope']else'incomplete_selected_scope'
    state['elapsed_seconds']=round(time.monotonic()-begin,3);save(out/'benchmark.json',state)
    print(json.dumps(state,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
