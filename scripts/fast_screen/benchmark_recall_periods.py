"""Frozen cross-period raw-workbook screening experiment; no report writing.

One sequential model worker. Review all nominations from selected complete
articles. Budgets bound real execution, not asserted completion. No baseline
report is read. The adapter is optional; business tasks are ordinary JSON.
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
from portable_screen import load,save,digest,prepare,run,segments,resolve_range
from refined_filter import refine
from opinion_gate import select
from conservative_filter import csv_write
from recover_more_views import normalize,POLICY,FIELDS

HERE=Path(__file__).resolve().parent
CODE_FILES=['benchmark_recall_periods.py','portable_screen.py','refined_filter.py',
            'opinion_gate.py','conservative_filter.py','recover_more_views.py','codex_json_transport.py']

def frozen_signature():
    result={name:digest((HERE/name).read_text(encoding='utf-8')) for name in CODE_FILES}
    result['prepare_records.py']=digest((HERE.parent/'cwh_strict_screen/prepare_records.py').read_text(encoding='utf-8'))
    return result

def prepare_review(model,out,max_chars=90000):
    rows=load(model/'sources.json');agenda=load(model/'agenda.json');views=load(model/'views.json')
    source={r['id']:r for r in rows};counts=Counter();candidates=[]
    for v in views:
        counts[v['id']]+=1
        fixed=normalize(source[v['id']],v,agenda)
        fixed.update(candidate_id=v['id']+':'+str(counts[v['id']]),original_nomination_hash=digest(v))
        candidates.append(fixed)
    batches=[];batch=[];size=0
    for id in dict.fromkeys(v['id'] for v in candidates):
        r=source[id]
        group={'id':id,'title':r['title'],'account':r.get('account',''),'published_at':r.get('published_at',''),
               'paragraphs':[{'id':s['id'],'text':s['text']} for s in segments(r)],
               'nominations':[{k:v.get(k) for k in ['candidate_id',*FIELDS,'repair_proposals']} for v in candidates if v['id']==id]}
        n=len(json.dumps(group,ensure_ascii=False))
        if n>max_chars:raise ValueError('Complete review article exceeds capacity; do not truncate')
        if batch and size+n>max_chars:batches.append(batch);batch=[];size=0
        batch.append(group);size+=n
    if batch:batches.append(batch)
    save(out/'candidates.json',candidates);save(out/'sources.json',rows);save(out/'agenda.json',agenda)
    task_hashes={}
    for i,batch in enumerate(batches,1):
        packet={'policy':POLICY,'agenda':agenda,'articles':batch,
                'expected_candidate_ids':[v['candidate_id'] for a in batch for v in a['nominations']]}
        name=f'review-{i:03d}.json';save(out/'tasks'/name,packet);task_hashes[name]=digest(packet)
    props={k:{'type':'string'} for k in ['candidate_id','decision','reason','original_date']}
    props['decision']['enum']=['retain','exclude','needs_source_identity','needs_rewrite']
    props['date_evidence']={'type':'array','items':{'type':'string'}}
    save(out/'response_schema.json',{'type':'object','additionalProperties':False,'required':['items'],
         'properties':{'items':{'type':'array','items':{'type':'object','additionalProperties':False,'required':list(props),'properties':props}}}})
    save(out/'manifest.json',{'sources_hash':digest(rows),'candidates_hash':digest(candidates),'agenda_hash':digest(agenda),
                             'policy_hash':digest(POLICY),'task_hashes':task_hashes})
    return {'nominations':len(candidates),'review_batches':len(batches),'review_articles':len({v['id'] for v in candidates})}

def ingest_review(out):
    m=load(out/'manifest.json');rows=load(out/'sources.json');c=load(out/'candidates.json');a=load(out/'agenda.json')
    from review_policy_versions import BY_HASH
    if m['policy_hash']not in BY_HASH:raise ValueError('Unregistered review policy')
    expected_policy=BY_HASH[m['policy_hash']]
    for k,v in [('sources_hash',rows),('candidates_hash',c),('agenda_hash',a)]:
        if digest(v)!=m[k]:raise ValueError('Changed review snapshot')
    byid={v['candidate_id']:v for v in c};sources={r['id']:r for r in rows};seen={};invalid=[];scheduled=[]
    for name,hash in m['task_hashes'].items():
        packet=load(out/'tasks'/name)
        if digest(packet)!=hash:raise ValueError('Changed or truncated review task')
        if packet['policy']!=expected_policy:raise ValueError('Review task policy differs from registered contract')
        ids=packet['expected_candidate_ids'];scheduled.extend(ids)
        path=out/'responses'/name
        if not path.exists():continue
        try:
            response=load(path)
            if set(response)!={'items'}:raise ValueError('Invalid response root')
            local={}
            for item in response['items']:
                id=item['candidate_id']
                if id not in ids or id in local or id in seen:raise ValueError('Unknown/duplicate review ID')
                if set(item)!={'candidate_id','decision','reason','original_date','date_evidence'}:raise ValueError('Invalid review fields')
                if item['decision']not in {'retain','exclude','needs_source_identity','needs_rewrite'}:raise ValueError('Invalid decision')
                if any(not isinstance(item[k],str) for k in ['candidate_id','decision','reason','original_date']) or not isinstance(item['date_evidence'],list):raise ValueError('Invalid types')
                local[id]=item
            seen.update(local)
        except (ValueError,KeyError,TypeError) as e:invalid.append({'task':name,'error':str(e)})
    if Counter(scheduled)!=Counter(byid.keys()):raise ValueError('Review plan coverage differs')
    reviewed=[]
    for id,d in seen.items():
        v=byid[id];errors=list(v['errors']);date=d['original_date'];excerpt=''
        if date:
            try:
                datetime.strptime(date,'%Y-%m-%d');start,end=resolve_range(d['date_evidence'],segments(sources[v['id']]));excerpt=sources[v['id']]['content'][start:end]
                if not a['window_start'][:10]<=date<=a['window_end'][:10]:errors.append('old_original')
            except (ValueError,TypeError):errors.append('invalid_review_date_anchor')
        elif d['date_evidence']:errors.append('review_date_without_date')
        reviewed.append({**v,'errors':errors,'independent_decision':d['decision'],'independent_reason':d['reason'],
                         'review_original_date':date,'review_date_excerpt':excerpt,'formal_ready':False})
    kept=[v for v in reviewed if v['independent_decision']=='retain' and not v['errors'] and v.get('report_sentence')]
    save(out/'reviewed_candidates.json',reviewed);save(out/'source_check_candidates.json',kept)
    lines=['原文支持的待溯源候选；不是正式可引用清单。','同主体多条不同观点及同篇跨议题观点全部保留，不提前套正文选用上限。','']
    for topic in a['topics']:
        values=[v for v in kept if v['topic']==topic];lines.extend([f'{topic}（{len(values)}条）',''])
        for v in values:
            r=sources[v['id']];lines.extend([v['report_sentence'],f"编号：{v['candidate_id']}；来源标题：{r['title']}；监测时间：{r['published_at']}",f"监测链接：{r['url']}",''])
        if not values:lines.extend(['本轮未取得通过的待溯源候选。',''])
    (out/'分议题待溯源候选.txt').write_text('\n'.join(lines),encoding='utf-8')
    result={'nominated':len(c),'reviewed':len(reviewed),'unreviewed':[id for id in byid if id not in seen],
            'invalid_responses':invalid,'decisions':dict(Counter(v['independent_decision'] for v in reviewed)),
            'semantic_retains_with_field_errors':sum(v['independent_decision']=='retain' and bool(v['errors']) for v in reviewed),
            'source_check_claims':len(kept),'distinct_source_articles':len({v['id'] for v in kept}),
            'speaker_topic_pairs':len({(v['topic'],v['kind'],v['name']) for v in kept}),
            'claims_by_topic':{t:sum(v['topic']==t for v in kept) for t in a['topics']},'formal_ready':0}
    save(out/'summary.json',result);return result

def bounded_call(argv,packet,out,deadline):
    start=time.monotonic();out.parent.mkdir(parents=True,exist_ok=True)
    with out.with_suffix('.stderr.log').open('w',encoding='utf-8') as err, out.open('w',encoding='utf-8') as stdout:
        child=subprocess.Popen(argv,stdin=subprocess.PIPE if packet is not None else subprocess.DEVNULL,
                               stdout=stdout,stderr=err,text=True,encoding='utf-8',cwd=HERE)
        try:
            child.communicate(json.dumps(packet,ensure_ascii=False) if packet is not None else None,
                              timeout=max(.1,deadline-time.monotonic()));code=child.returncode
        except subprocess.TimeoutExpired:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:child.kill()
            child.communicate();code=124
    return {'seconds':round(time.monotonic()-start,3),'exit_code':code}

def main():
    p=argparse.ArgumentParser();p.add_argument('--workbook',type=Path,required=True);p.add_argument('--agenda',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--model',default='gpt-6.1-sol');p.add_argument('--budget-seconds',type=int,default=480)
    p.add_argument('--frozen-rules',type=Path,required=True);args=p.parse_args();out=args.out.resolve()
    if out.exists():raise ValueError('Fresh experiment directory required')
    if frozen_signature()!=load(args.frozen_rules):raise ValueError('Rules changed after cross-period freeze')
    out.mkdir(parents=True);begin=time.monotonic();deadline=begin+args.budget_seconds
    state={'started_at':datetime.now(timezone.utc).isoformat(),'model':args.model,'budget_seconds':args.budget_seconds,
           'mode':'all_leads_full_articles_then_all_nominations_independent_review','cache_reuse':False,
           'scope':'Raw workbook normalization + script selection + up to99 full articles + review all nominations; excludes public-web verification and report writing.',
           'frozen_rules_hash':digest(load(args.frozen_rules)),'calls':[],'formal_ready':0}
    save(out/'benchmark.json',state)
    normalizer=HERE.parent/'cwh_strict_screen/prepare_records.py'
    timing=bounded_call([sys.executable,str(normalizer),'--workbook',str(args.workbook.resolve()),'--out',str(out/'records.json')],None,out/'normalization.stdout.json',deadline)
    state['calls'].append({'stage':'normalization',**timing});save(out/'benchmark.json',state)
    if timing['exit_code']:raise RuntimeError('Normalization failed; inspect logs')
    records=load(out/'records.json');agenda=load(args.agenda)
    start=time.monotonic();remaining,base_audit,base_summary=refine(records,agenda)
    chosen,audit,summary,index=select(remaining,agenda,max_body_chars=650000)
    save(out/'filter/base_summary.json',base_summary);csv_write(out/'filter/base_audit.csv',base_audit)
    save(out/'filter/remaining_records.json',remaining);save(out/'filter/summary.json',summary)
    csv_write(out/'filter/priority_audit.csv',audit);save(out/'filter/evidence_index.json',index)
    packets=prepare(chosen,agenda,out/'model',90000,args.model,mode='all_leads')
    state.update(input_rows=len(records),base_remaining=len(remaining),selected_articles=len(chosen),
                 selected_body_characters=sum(len(r['content']) for r in chosen),first_batches=packets['batches'],
                 script_seconds=round(time.monotonic()-start,3))
    save(out/'benchmark.json',state);print(json.dumps({'stage':'script','rows':len(records),'remaining':len(remaining),'selected':len(chosen),'seconds':state['script_seconds']}),flush=True)
    command=[sys.executable,str(HERE/'codex_json_transport.py'),'--model',args.model]
    first_begin=time.monotonic();state['reading']=run(out/'model',command,max(0,min(300,deadline-time.monotonic()-100)))
    state['reading_wall_seconds']=round(time.monotonic()-first_begin,3)
    save(out/'benchmark.json',state);print(json.dumps({'stage':'reading','summary':state['reading']},ensure_ascii=False),flush=True)
    state['review_plan']=prepare_review(out/'model',out/'review')
    for task in sorted((out/'review/tasks').glob('*.json')):
        if time.monotonic()>=deadline:break
        timing=bounded_call(command+['--schema-file',str(out/'review/response_schema.json')],load(task),out/(task.stem+'.stdout.json'),deadline)
        state['calls'].append({'stage':task.stem,**timing});save(out/'benchmark.json',state)
        print(json.dumps(state['calls'][-1]),flush=True)
        if timing['exit_code']:break
        try:save(out/'review/responses'/task.name,load(out/(task.stem+'.stdout.json')))
        except (ValueError,OSError):break
    state['review']=ingest_review(out/'review')
    state.update(elapsed_seconds=round(time.monotonic()-begin,3),
                 complete_selected_scope=not state['reading']['unread_ids'] and not state['reading']['invalid_responses'] and not state['review']['unreviewed'] and not state['review']['invalid_responses'])
    state['status']='completed_selected_scope_pending_source_verification' if state['complete_selected_scope'] else 'incomplete_selected_scope'
    save(out/'benchmark.json',state);print(json.dumps(state,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
