"""Lossless output-field compression, with a model-neutral JSON host bridge.

Complete source paragraphs remain unchanged. Only topic/ID/enumeration fields
and repeated actor metadata are represented compactly, then expanded by code.
"""
import argparse,copy,json,subprocess,sys
from pathlib import Path
from portable_screen import load,save,digest
from recall_v8_policy import EXTRACTION_POLICY

KINDS={'p':'person','j':'joint_people','a':'account','i':'institution'}
SOURCES={'o':'original','r':'reprint','c':'compilation','u':'unclear'}
CODES={'h':'has_view','o':'official_only','n':'news_only','t':'trading_only','u':'unrelated','z':'no_independent_analysis'}
DECISIONS={'r':'retain','e':'exclude','i':'needs_source_identity','w':'needs_rewrite'}

def obj(properties):return {'type':'object','additionalProperties':False,'required':list(properties),'properties':properties}
def string():return {'type':'string'}
def arr(item):return {'type':'array','items':item}
def enumeration(values):return {'type':'string','enum':list(values)}
def numbers():return arr({'type':'integer'})

def schema(packet,review):
    if review:
        return obj({'items':arr(obj({'i':{'type':'integer'},'d':enumeration(DECISIONS),'r':string(),'t':string(),'e':numbers()}))})
    claim=obj({'c':string(),'e':numbers(),'d':string(),'x':numbers()})
    group=obj({'t':enumeration(packet['agenda']['topics']),'k':enumeration(KINDS),
               'n':string(),'r':string(),'i':numbers(),'s':enumeration(SOURCES),'a':{'type':'boolean'},'q':arr(claim)})
    return obj({'items':arr(obj({'i':string(),'c':enumeration(CODES),'g':arr(group)}))})

def encode(packet):
    api=copy.deepcopy(packet);review='expected_candidate_ids'in packet
    if review:
        ids=packet['expected_candidate_ids'];mapping={cid:n for n,cid in enumerate(ids,1)}
        for article in api['articles']:
            for nomination in article['nominations']:
                nomination['candidate_id']=mapping[nomination['candidate_id']]
        api['expected_candidate_ids']=list(range(1,len(ids)+1))
        api['policy']=packet['policy']+'''
本次只压缩返回格式，不改变判断标准。输入candidate_id已替换为本批整数键，必须逐一覆盖。
返回JSON {"items":[{"i":整数candidate_id,"d":"r/e/i/w","r":"关键审查理由≤60字","t":"原发日或空字符串","e":[原日期段号整数]}]}。
d的r=retain、e=exclude、i=needs_source_identity、w=needs_rewrite；r字段是理由；t是original_date；e是date_evidence。
段号整数对应本篇rXXX:pN中的N，不是字符偏移，不得引用其他文章。没有明确日期时t=""、e=[]。不重写claim，不改变观点和条件。只返回此紧凑格式，不返回旧字段名。'''
    else:
        # Keep semantic rules and replace only the redundant output contract.
        semantic=[]
        for line in packet['policy'].splitlines():
            if line.startswith(('每篇恰好返回id','views字段')):continue
            if line.startswith('证据段号'):
                line=line.split('每篇恰好一条记录')[0]
            semantic.append(line)
        api['policy']='\n'.join(semantic)+'''
返回格式用以下紧凑字段，语义要求不变。逐一覆盖expected_article_ids，每篇一个items条目。
{"items":[{"i":"原文章id","c":"h/o/n/t/u/z","g":[{"t":"完整中文议题名","k":"p/j/a/i","n":"主体姓名或全称","r":"完整机构职务","i":[身份起止段号整数],"s":"o/r/c/u","a":true,"q":[{"c":"完整观点","e":[证据起止段号整数],"d":"明确原发日或空字符串","x":[原日期段号整数]}]}]}]}
文章c：h=has_view,o=official_only,n=news_only,t=trading_only,u=unrelated,z=no_independent_analysis；无观点g=[]。
只要g非空，文章c必须=h；主要谈行情的综合文章若提取了其中合格的政策分析，也填h。没有合格观点时才能填其他代码且g=[]。
同篇、同议题、同主体且机构职务、归属相同的观点放在一个g组，q逐条保存真正不同的完整判断，不把同义转述、同一判断的原因与结论拆成多条。元数据不同另起组，不得合并不同发言人。
组t逐字填写agenda.topics中与本条分析真正相关的完整中文议题名，不填数字，不用文章其他部分的话题替代本条对象。同一主体跨不同议题分别成组；k：p=person,j=joint_people,a=account,i=institution；n=name,r=role,i=identity。
s：o=original,r=reprint,c=compilation,u=unclear；a=true表示explicit，false表示uncertain。
q中c=claim,e=evidence,d=original_date,x=date_evidence。日期按每条观点分别填写，不用分组日期替代。
d非空时x必须是支持该观点原发日的本篇起止段号；没有明确日期证据则d=""且x=[]。e、i、x只需起止两个整数，同段写两次，不列长段号清单。
所有段号整数对应本篇rXXX:pN中的N；无需重复文章id，不是字符偏移。未知身份或日期段号用[]。
完整机构职务、联合作者逐人姓名前缀、身份及原创归属仍须原文支持，不能为压缩格式省略或猜补。只返回此格式，不返回旧字段名。'''
    api['output_schema']=schema(packet,review)
    return api

def paragraph_ids(values,article):
    if not isinstance(values,list)or any(type(n)is not int or n<1 for n in values):raise ValueError('Invalid compact paragraph indices')
    allowed={p['id']for p in article['paragraphs']};ids=[article['id']+':p'+str(n)for n in values]
    if any(id not in allowed for id in ids):raise ValueError('Unknown compact paragraph index')
    return ids

def decode(packet,response):
    if not isinstance(response,dict)or set(response)!={'items'}or not isinstance(response['items'],list):raise ValueError('Invalid compact response')
    articles={a['id']:a for a in packet['articles']};seen=set();items=[]
    if 'expected_candidate_ids'in packet:
        expected=packet['expected_candidate_ids'];location={n['candidate_id']:a for a in packet['articles']for n in a['nominations']}
        for item in response['items']:
            if set(item)!={'i','d','r','t','e'}or type(item['i'])is not int or not 1<=item['i']<=len(expected):raise ValueError('Invalid compact review key')
            cid=expected[item['i']-1]
            if cid in seen or item['d']not in DECISIONS or not isinstance(item['r'],str)or not isinstance(item['t'],str):raise ValueError('Invalid compact review')
            seen.add(cid);items.append({'candidate_id':cid,'decision':DECISIONS[item['d']],'reason':item['r'],
                'original_date':item['t'],'date_evidence':paragraph_ids(item['e'],location[cid])})
        return {'items':items}
    topics=packet['agenda']['topics']
    for item in response['items']:
        if set(item)!={'i','c','g'}or item['i']not in articles or item['i']in seen or item['c']not in CODES or not isinstance(item['g'],list):raise ValueError('Invalid compact article')
        id=item['i'];seen.add(id);article=articles[id];views=[]
        for g in item['g']:
            if set(g)!={'t','k','n','r','i','s','a','q'}or not isinstance(g['t'],str)or g['t']not in topics:raise ValueError('Invalid compact topic/group')
            if g['k']not in KINDS or g['s']not in SOURCES or type(g['a'])is not bool or any(not isinstance(g[k],str)for k in ['n','r'])or not isinstance(g['q'],list)or not g['q']:raise ValueError('Invalid compact group metadata')
            identity=paragraph_ids(g['i'],article)
            for q in g['q']:
                if set(q)!={'c','e','d','x'}or not isinstance(q['c'],str)or not isinstance(q['d'],str):raise ValueError('Invalid compact claim')
                views.append({'topic':g['t'],'kind':KINDS[g['k']],'name':g['n'],'role':g['r'],'claim':q['c'],
                    'evidence':paragraph_ids(q['e'],article),'identity':identity,'source_kind':SOURCES[g['s']],
                    'attribution':'explicit'if g['a']else'uncertain','original_date':q['d'],'date_evidence':paragraph_ids(q['x'],article)})
        # Preserve a category/views conflict for canonical per-article intake.
        # It remains invalid/unread; other articles in the batch stay usable.
        items.append({'id':id,'code':CODES[item['c']],'views':views})
    return {'items':items}

def compress_known_response(packet,response):
    """Offline round-trip diagnostic; not a source of new semantic decisions."""
    number=lambda ids:[int(id.rsplit(':p',1)[1])for id in ids]
    reverse=lambda values:{v:k for k,v in values.items()}
    if 'expected_candidate_ids'in packet:
        index={cid:n for n,cid in enumerate(packet['expected_candidate_ids'],1)}
        return {'items':[{'i':index[v['candidate_id']],'d':reverse(DECISIONS)[v['decision']],'r':v['reason'],
                          't':v['original_date'],'e':number(v['date_evidence'])}for v in response['items']]}
    topics=packet['agenda']['topics'];items=[]
    for item in response['items']:
        groups=[];previous=None
        for v in item['views']:
            key=tuple(v[k]if not isinstance(v[k],list)else tuple(v[k])for k in ['topic','kind','name','role','identity','source_kind','attribution'])
            if not groups or key!=previous:
                groups.append({'t':v['topic'],'k':reverse(KINDS)[v['kind']],'n':v['name'],'r':v['role'],
                    'i':number(v['identity']),'s':reverse(SOURCES)[v['source_kind']],'a':v['attribution']=='explicit','q':[]})
            groups[-1]['q'].append({'c':v['claim'],'e':number(v['evidence']),'d':v['original_date'],'x':number(v['date_evidence'])})
            previous=key
        items.append({'i':item['id'],'c':reverse(CODES)[item['code']],'g':groups})
    return {'items':items}

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',default='gpt-6.1-sol');p.add_argument('--host-command-json')
    p.add_argument('--audit-dir',type=Path,required=True);p.add_argument('--profile-manifest',type=Path,required=True);a=p.parse_args()
    manifest=load(a.profile_manifest)
    if digest(Path(__file__).read_text(encoding='utf-8'))!=manifest['bridge_hash']:raise ValueError('Compact bridge changed')
    packet=json.load(sys.stdin);api=encode(packet);key=digest(packet)
    save(a.audit_dir/(key+'.request.json'),api)
    host=json.loads(a.host_command_json)if a.host_command_json else[sys.executable,str(Path(__file__).with_name('codex_json_transport.py')),'--model',a.model]
    if not isinstance(host,list)or not host or not all(isinstance(s,str)for s in host):raise ValueError('Host must be argv list')
    result=subprocess.run(host,input=json.dumps(api,ensure_ascii=False),text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode:
        save(a.audit_dir/(key+'.failure.json'),{'exit_code':result.returncode});raise SystemExit(result.returncode)
    raw_path=a.audit_dir/(key+'.host_stdout.txt')
    raw_path.write_text(result.stdout,encoding='utf-8')
    from portable_screen import load_response
    raw,parser_notes=load_response(raw_path);save(a.audit_dir/(key+'.compact_response.json'),raw)
    from localize_native_decode import decode_articles
    expanded,localized_errors=decode_articles(packet,raw,decode)
    save(a.audit_dir/(key+'.expanded_response.json'),expanded)
    if localized_errors:save(a.audit_dir/(key+'.localized_errors.json'),localized_errors)
    save(a.audit_dir/(key+'.receipt.json'),{'canonical_task_hash':key,'compact_task_hash':digest(api),'compact_response_hash':digest(raw),
        'expanded_response_hash':digest(expanded),'bridge_hash':manifest['bridge_hash'],'parser_notes':parser_notes,'localized_errors':localized_errors})
    print(json.dumps(expanded,ensure_ascii=False))

if __name__=='__main__':main()
