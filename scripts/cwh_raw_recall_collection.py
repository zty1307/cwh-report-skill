"""Durable multi-topic reading of a small, previously unread raw batch."""
import hashlib,json,os,sys,time
from pathlib import Path
from cwh_pipeline_runtime import atomic_write_json
from cwh_prepared_research import digest
from cwh_scoped_process import run_scoped_command
from cwh_screen_bridge import materialize_screen

def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def collect_subset(workspace,records,originals,agenda,model,deadline,maximum_seconds=150):
    workspace=Path(workspace);workspace.mkdir(parents=True,exist_ok=True)
    key=digest({'records':records,'agenda':read(agenda),'model':model,
        'rules':sha(Path(__file__).parent/'fast_screen/collection_frozen_rules.json')})
    receipt=workspace/'completed_collection.json';out=workspace/'job'
    if receipt.exists():
        cached=read(receipt)
        if cached['key']!=key or any(not Path(p).is_file() or sha(p)!=h for p,h in cached['artifacts'].items()):
            raise ValueError('Raw recall completed checkpoint changed')
        reused=True
    else:
        reused=out.exists()
        if out.exists():
            launch=read(out.with_suffix('.native_launch.json'))
            sources=read(out/'model/sources.json');expected={r['id']:r for r in records}
            if (not launch.get('run_requested') or launch.get('requested_model')!=model
                    or {r['id'] for r in sources}!=set(expected)
                    or any(r['content']!=expected[r['id']]['content'] for r in sources)
                    or not (out/'results_guarded/candidates_pending_independent_review.json').is_file()
                    or read(workspace/'identity.json')['key']!=key):
                raise ValueError('Incomplete raw recall requires diagnosis; refuse blind repeat')
        else:
            allowance=min(maximum_seconds,int(deadline-time.time()-10))
            if allowance<45:raise TimeoutError('Raw recall reading opportunity exhausted before dispatch')
            atomic_write_json(workspace/'identity.json',{'key':key})
            atomic_write_json(workspace/'records.json',records)
            command=[sys.executable,str(Path(__file__).parent/'fast_screen/native_screen_samples.py'),
                '--model',model,'--records',str(workspace/'records.json'),'--agenda',str(agenda),
                '--out',str(out),'--budget-seconds',str(allowance),'--run']
            with (workspace/'screen.log').open('w',encoding='utf-8') as log:
                code=run_scoped_command(command,cwd=workspace,env=os.environ.copy(),stdout=log,
                                        timeout=min(allowance+8,deadline-time.time()))
            if code:
                from cwh_host_research import HostModelError
                raise HostModelError('Raw reserve collection incomplete; preserve its exact input',code)
        atomic_write_json(receipt,{'key':key,'artifacts':{str(p):sha(p) for p in out.rglob('*') if p.is_file()}})
    bytopic,quarantine,runs=materialize_screen(out,originals,read(agenda)['topics'])
    completed=read(out/'model/article_decisions.json')
    return bytopic,quarantine,[{**r,'cache_reused':reused} for r in runs],{
        'submitted_ids':[r['id'] for r in records], 'completed_ids':[r['id'] for r in completed],
        'reused_completed_collection':reused,'collection_receipt':str(receipt),
        'quarantine_count':len(quarantine),'scope':'Full multi-topic reading; independent report review still required'}
