"""Reuse real full-article screenings inside the report author, never approve them."""
import copy, hashlib, json, subprocess, sys, time, uuid, os
from pathlib import Path

def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),'utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def prepare_screen(task,plan,index,deadline,maximum_seconds=None):
    stage=Path(task['stage_workspace']);root=stage/'sample_screen'
    corpus_path=Path(task['inputs']['public_corpus_index']).with_name('public_article_evidence.json')
    if sha(corpus_path)!=index['source_sha256']:raise ValueError('Screen corpus changed')
    receipt=root/'integration_receipt.json'
    if receipt.exists():
        r=read(receipt)
        if r['corpus_sha256']!=sha(corpus_path):raise ValueError('Screen input hash changed')
        for name,digest in r['artifacts'].items():
            if sha(root/name)!=digest:raise ValueError('Screen output changed: '+name)
        return read(root/'bridge.json')
    if root.exists():raise ValueError('Incomplete screening checkpoint requires diagnosis; refuse blind replay')
    root.mkdir()
    corpus=read(corpus_path);topics=[t['topic'] for t in plan['topics']]
    records=[];originals={}
    for n,row in enumerate(corpus['candidates'],2):
        rid=f'r{n}';originals[rid]=row
        records.append({'id':rid,'title':row.get('title',''),'content':row.get('content',''),
            'url':row.get('url',''),'published_at':row.get('published_at',''),
            'account':row.get('account') or row.get('source',''),'site':'公众号',
            'content_sha256':hashlib.sha256(row.get('content','').encode()).hexdigest()})
    agenda={'meeting_date':plan['monitoring_period']['start'][:10],
        'window_start':plan['monitoring_period']['start'],'window_end':plan['monitoring_period']['end'],
        'topics':topics,'topic_aliases':corpus.get('topic_aliases') or [[t] for t in topics]}
    write(root/'records.json',records);write(root/'agenda.json',agenda)
    tool=Path(__file__).parent/'fast_screen'
    allowance=min(360,max(0,int(deadline-time.monotonic()-240)))
    if maximum_seconds is not None:
        allowance=min(allowance,max(0,int(maximum_seconds)))
    if allowance<30:
        if maximum_seconds is None:
            raise TimeoutError('No remaining screening budget; original clock retained')
        result={'topics':{t:[] for t in topics},'quarantine':[],'runs':[],
                'state':{'status':'not_invoked_protected_web_budget','selected_articles':0,
                         'unread_corpus_records':len(records)},'seconds':0,'formal_ready':False}
        write(root/'bridge.json',result)
        write(receipt,{'corpus_sha256':sha(corpus_path),'artifacts':{'bridge.json':sha(root/'bridge.json')},
                       'scope':'Raw model call not dispatched; preserve web budget and original clock. All raw originals remain unread.'})
        return result
    model=os.environ.get('CWH_SCREEN_MODEL','')
    if not model:raise ValueError('Configure CWH_SCREEN_MODEL explicitly in the host; no model fallback')
    command=[sys.executable,str(tool/'native_screen_samples.py'),'--model',model,'--records',str(root/'records.json'),
        '--agenda',str(root/'agenda.json'),'--out',str(root/'job'),'--budget-seconds',str(allowance),'--run']
    began=time.monotonic()
    with (root/'screen.log').open('w',encoding='utf-8') as log:
        proc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=allowance+12)
    if proc.returncode:
        from cwh_host_research import HostModelError
        raise HostModelError('Standalone screening failed; see retained screen.log',proc.returncode)
    job=root/'job';state=read(job/'benchmark.json')
    bytopic,quarantine,actual=materialize_screen(job,originals,topics)
    result={'topics':bytopic,'quarantine':quarantine,'runs':actual,'state':state,
        'seconds':round(time.monotonic()-began,3),'formal_ready':False}
    write(root/'bridge.json',result)
    names=['bridge.json','job/benchmark.json','job/model/sources.json','job/model/article_decisions.json',
        'job/results_guarded/candidates_pending_independent_review.json','job/model/runtime.json']
    for folder in ['job/model/tasks','job/model/responses','job/model/receipts','job/host_audit']:
        names.extend(str(p.relative_to(root)) for p in (root/folder).rglob('*') if p.is_file())
    write(receipt,{'corpus_sha256':sha(corpus_path),'artifacts':{n:sha(root/n) for n in names},
        'scope':'Extraction reuse only; unchanged independent report verification remains mandatory'})
    return result

def packet_readings(packet,screen):
    items={r['record_id']:r for r in packet['items'] if r['origin']=='raw_monitoring'}
    out=[]
    for row in screen['topics'][packet['topic']]:
        rid=row['record']['record_id']
        if rid not in items:raise ValueError('Missing screened original in report packet')
        if row['record']['content']!=items[rid]['content']:raise ValueError('Report source differs from screened source')
        out.append({'id':items[rid]['id'],**copy.deepcopy(row['decision'])})
    return out


def materialize_screen(job,originals,topics):
    tool=Path(__file__).parent/'fast_screen'
    candidates=read(job/'results_guarded/candidates_pending_independent_review.json')
    sources={r['id']:r for r in read(job/'model/sources.json')}
    article_decisions=read(job/'model/article_decisions.json')
    bytopic={t:[] for t in topics};quarantine=[]
    for dec in article_decisions:
        src=sources[dec['id']];original=originals[dec['id']]
        if src['content']!=original['content']:raise ValueError('Screen full text changed')
        for ti,topic in enumerate(topics,1):
            if ti not in original.get('topic_hits',[]):continue
            claims=[]
            for v in candidates:
                if v['id']!=dec['id'] or v['topic']!=topic:continue
                if v['errors'] or v['kind']=='joint_people':
                    quarantine.append({'candidate':v,'reason':'pending_fields_or_joint_identity'});continue
                start,end=v['excerpt_start'],v['excerpt_end']
                # Keep identity and argument in one original continuous envelope.
                if v.get('identity'):
                    sys.path.insert(0,str(tool))
                    from portable_screen import resolve_range,segments
                    try:
                        a,b=resolve_range(v['identity'],segments(src))
                    except ValueError as exc:
                        quarantine.append({'candidate':v,'reason':'invalid_identity_paragraph_range',
                                           'validation_problem':str(exc)})
                        continue
                    start=min(start,a);end=max(end,b)
                quote=src['content'][start:end]
                if v['kind']=='person' and (v['name'] not in quote or v['role'] not in quote):
                    quarantine.append({'candidate':v,'reason':'identity_not_literal_in_continuous_excerpt'});continue
                claims.append({'speaker':v['name'],'role':v['role'],
                    'speaker_type':'named_person' if v['kind']=='person' else ('self_media' if v['kind']=='account' else 'media_voice'),
                    'claim':v['claim'],'quote':quote,'cluster':'screen_pending',
                    'screen_candidate_id':v['candidate_id']})
            bytopic[topic].append({'record':original,'decision':{'decision':'eligible' if claims else 'excluded',
                'reason':'完整原文初筛提名，尚待编排及独立复核' if claims else
                    ('完整原文已读，本题未取得字段完整提名；其他议题及待补项另存，不据此断言整篇没有观点' if dec['code']=='has_view' else '完整原文初筛：'+dec['code']),
                'relevant':bool(claims),'claims':claims},'screen_id':dec['id']})
    actual=[]
    for p in sorted((job/'host_audit').glob('*/receipt.json')):
        rec=read(p)
        if rec.get('status')!='completed_json':continue
        actual.append({'session_id':rec['run_id'],'seconds':rec.get('seconds',0),
            'transport':'standalone_fulltext_screen','model_invoked':True,'receipt':str(p),
            'reported_models':rec.get('reported_models',[])})
    return bytopic,quarantine,actual
