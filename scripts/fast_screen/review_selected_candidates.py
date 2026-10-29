"""Fresh independent full-source review of explicitly selected candidate IDs."""
import argparse,json,time
from pathlib import Path
from portable_screen import load,save,digest
from benchmark_recall_periods import ingest_review,bounded_call
from run_optimized_screen import complete_pool

def prepare_selection(queue,ids,out,policy_version='base'):
    manifest=load(queue/'manifest.json');candidates=load(queue/'candidates.json')
    if digest(candidates)!=manifest['candidates_hash']:raise ValueError('Changed candidates')
    if digest(load(queue/'sources.json'))!=manifest['sources_hash']or digest(load(queue/'agenda.json'))!=manifest['agenda_hash']:raise ValueError('Changed source or agenda')
    if not ids or len(ids)!=len(set(ids))or not set(ids).issubset({v['candidate_id']for v in candidates}):raise ValueError('Unknown/duplicate/empty selected IDs')
    if out.exists():raise ValueError('Fresh review directory required')
    from review_policy_versions import VERSIONS,BY_HASH
    if manifest['policy_hash']not in BY_HASH or policy_version not in VERSIONS:raise ValueError('Unknown review policy')
    policy=VERSIONS[policy_version];hashes={};scheduled=[]
    for name,h in manifest['task_hashes'].items():
        packet=load(queue/'tasks'/name)
        if digest(packet)!=h:raise ValueError('Changed full-source review task')
        articles=[]
        for article in packet['articles']:
            vals=[v for v in article['nominations']if v['candidate_id']in ids]
            if vals:articles.append({**article,'nominations':vals})
        if not articles:continue
        packet={**packet,'policy':policy,'articles':articles,'expected_candidate_ids':[v['candidate_id']for r in articles for v in r['nominations']]}
        scheduled.extend(packet['expected_candidate_ids']);save(out/'tasks'/name,packet);hashes[name]=digest(packet)
    if set(scheduled)!=set(ids)or len(scheduled)!=len(ids):raise ValueError('Selection coverage mismatch')
    subset=[v for v in candidates if v['candidate_id']in ids]
    for name in ['sources.json','agenda.json','response_schema.json']:save(out/name,load(queue/name))
    save(out/'candidates.json',subset)
    save(out/'manifest.json',{**manifest,'policy_hash':digest(policy),'candidates_hash':digest(subset),'task_hashes':hashes})
    save(out/'selection_receipt.json',{'source_queue_manifest_hash':digest(manifest),'selected_ids':ids,
        'selection_is_semantic_approval':False,'full_source_preserved':True,'review_policy_version':policy_version})
    return len(hashes)

def main():
    p=argparse.ArgumentParser();p.add_argument('--queue',type=Path,required=True);p.add_argument('--ids',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--command-json');p.add_argument('--budget-seconds',type=int,default=180)
    p.add_argument('--policy-version',choices=['base','clarified'],default='clarified')
    a=p.parse_args();a.queue=a.queue.resolve();a.ids=a.ids.resolve();a.out=a.out.resolve()
    begin=time.monotonic();count=prepare_selection(a.queue,load(a.ids),a.out,a.policy_version)
    calls=[]
    if a.command_json:
        command=json.loads(a.command_json)
        if not isinstance(command,list)or not command or not all(isinstance(s,str)for s in command):raise ValueError('Host must be argv array')
        for task in sorted((a.out/'tasks').glob('*.json')):
            if time.monotonic()>=begin+a.budget_seconds:break
            path=a.out/(task.stem+'.stdout.json');timing=bounded_call(command,load(task),path,begin+a.budget_seconds)
            calls.append({'task':task.name,**timing})
            if timing['exit_code']:break
            try:save(a.out/'responses'/task.name,load(path))
            except ValueError:break
    state={'review_batches':count,'calls':calls,'review':ingest_review(a.out),'pool':complete_pool(a.out,a.out/'results'),
           'elapsed_seconds':round(time.monotonic()-begin,3),'formal_ready':0}
    save(a.out/'benchmark.json',state);print(json.dumps(state,ensure_ascii=False))

if __name__=='__main__':main()
