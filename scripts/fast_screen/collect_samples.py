"""Collection first: full-source nominations; no implicit semantic approval."""
import argparse,json,sys,time
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
from portable_screen import load,save,digest,prepare,run
from refined_filter import refine
from conservative_filter import csv_write
from opinion_gate_v8 import select,VERSION
from run_optimized_screen import signature as core_signature,schema_packets
from benchmark_recall_periods import prepare_review,bounded_call,HERE

EXTRA_FILES=['collect_samples.py','screen_samples.py','compact_screen_transport.py','canonical_screen_transport.py','workbuddy_screen_host.py','glm_wire_observer.cjs','review_selected_candidates.py']

def signature():
    return {**core_signature(),**{n:digest((HERE/n).read_text(encoding='utf-8'))for n in EXTRA_FILES}}

def export_collection(model,review,out):
    candidates=load(review/'candidates.json');sources={r['id']:r for r in load(model/'sources.json')}
    vals=[{**v,'independent_decision':'unreviewed','formal_ready':False}for v in candidates]
    save(out/'nominations_pending_review.json',vals)
    save(out/'field_repairs.json',[v for v in vals if v['errors']])
    lines=['初筛提名：全部尚未独立复核，也未核原始网页、身份及原发时间，不是可引用清单。',
           '真实不同判断分别保留；条数可能包含重复转载、近义判断，不能当作独立声音数量。','']
    topics=load(model/'agenda.json')['topics']
    for t in topics:
        rows=[v for v in vals if v['topic']==t];lines.extend([f'{t}（初筛提名{len(rows)}条）',''])
        for v in rows:
            r=sources[v['id']]
            lines.extend([v.get('report_sentence')or f"【身份或字段待补】{v.get('name','')}：{v['claim']}",
                f"编号：{v['candidate_id']}；状态：待独立复核"+('；字段问题：'+','.join(v['errors'])if v['errors']else''),
                f"原文标题：{r['title']}；监测时间：{r.get('published_at','')}",f"监测链接：{r.get('url','')}",''])
    (out/'分议题初筛提名_待复核.txt').write_text('\n'.join(lines),encoding='utf-8')
    return {'nominations':len(vals),'articles_with_nominations':len({v['id']for v in vals}),
        'speaker_topic_labels':len({(v['topic'],v['kind'],v['name'])for v in vals}),
        'field_complete_nominations':sum(not v['errors']for v in vals),'field_pending':sum(bool(v['errors'])for v in vals),
        'nominations_by_topic':dict(Counter(v['topic']for v in vals)),'independently_reviewed':0,'formal_ready':0}

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--workbook',type=Path);g.add_argument('--records',type=Path)
    p.add_argument('--agenda',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--frozen-rules',type=Path,required=True);p.add_argument('--model',required=True)
    p.add_argument('--command-json',required=True);p.add_argument('--budget-seconds',type=int,default=480)
    p.add_argument('--max-batch-chars',type=int,default=90000);p.add_argument('--run',action='store_true')
    p.add_argument('--max-body-chars',type=int,default=450000);p.add_argument('--reading-cost-power',type=float,default=.35)
    p.add_argument('--exploration-cost-power',type=float,default=0);p.add_argument('--max-batch-articles',type=int,default=0)
    p.add_argument('--max-selected-articles',type=int,default=99);a=p.parse_args()
    if signature()!=load(a.frozen_rules):raise ValueError('Collection rules changed: freeze a new profile')
    out=a.out.resolve()
    if out.exists():raise ValueError('Fresh job directory required')
    out.mkdir(parents=True);begin=time.monotonic();deadline=begin+a.budget_seconds
    state={'status':'preparing','mode':'collection_pending_independent_review','model':a.model,'policy':VERSION,
        'started_at':datetime.now(timezone.utc).isoformat(),'budget_seconds':a.budget_seconds,
        'rules_hash':digest(load(a.frozen_rules)),'cache_reuse':False,'calls':[],'formal_ready':0,
        'scope':'Script selection + complete article extraction + mechanical validation; no semantic approval, web verification or report writing.'}
    save(out/'benchmark.json',state)
    if a.workbook:
        norm=HERE/'prepare_records.py'
        if not norm.exists():norm=HERE.parent/'cwh_strict_screen/prepare_records.py'
        timing=bounded_call([sys.executable,str(norm),'--workbook',str(a.workbook.resolve()),'--out',str(out/'records.json')],None,out/'normalization.stdout.json',deadline)
        state['calls'].append({'stage':'normalization',**timing})
        if timing['exit_code']:raise RuntimeError('Normalization failed')
        records=load(out/'records.json')
    else:records=load(a.records);save(out/'records.json',records)
    start=time.monotonic();agenda=load(a.agenda);remaining,audit,base=refine(records,agenda)
    chosen,queue_audit,selection,index=select(remaining,agenda,a.max_selected_articles,a.max_body_chars,12,a.reading_cost_power,a.exploration_cost_power)
    save(out/'filter/base_summary.json',base);csv_write(out/'filter/base_audit.csv',audit)
    save(out/'filter/summary.json',selection);csv_write(out/'filter/priority_audit.csv',queue_audit)
    save(out/'filter/evidence_and_quote_aliases.json',index);save(out/'filter/remaining_records.json',remaining)
    info=prepare(chosen,agenda,out/'model',a.max_batch_chars,a.model,mode='recall_v8',max_articles_per_batch=a.max_batch_articles,batch_strategy='balanced' if a.max_batch_articles else 'greedy')
    state.update(input_rows=len(records),base_remaining=len(remaining),selected_articles=len(chosen),
        selected_body_characters=sum(len(r['content'])for r in chosen),batches=info['batches'],
        script_seconds=round(time.monotonic()-start,3),status='waiting_model')
    save(out/'benchmark.json',state);print(json.dumps({'stage':'script','model':a.model,'selected':len(chosen)}),flush=True)
    if a.run:
        command=json.loads(a.command_json)
        if not isinstance(command,list)or not command or not all(isinstance(s,str)for s in command):raise ValueError('Host must be argv array')
        start=time.monotonic();state['reading']=run(out/'model',command,max(0,deadline-time.monotonic()-15))
        state['reading_seconds']=round(time.monotonic()-start,3)
        # Preparing a review queue is mechanical, not a second AI pass.
        state['review_queue']=prepare_review(out/'model',out/'review_queue');schema_packets(out/'review_queue')
        state['collection']=export_collection(out/'model',out/'review_queue',out/'results')
        state['complete_selected_reading']=not state['reading']['unread_ids']and not state['reading']['invalid_responses']
        state['status']='collected_pending_independent_review'if state['complete_selected_reading']else'incomplete_reading_pending_independent_review'
    state['elapsed_seconds']=round(time.monotonic()-begin,3);save(out/'benchmark.json',state)
    print(json.dumps(state,ensure_ascii=False),flush=True)
    if a.run and not state['reading']['completed_articles']:
        runtime=load(out/'model/runtime.json')
        failures=[c for c in runtime.get('calls',[]) if c.get('exit_code')]
        if failures:raise SystemExit(failures[-1]['exit_code'])

if __name__=='__main__':main()
