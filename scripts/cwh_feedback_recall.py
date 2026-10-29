"""Schedule unread originals and feed real rejection records to discovery.

Scores are reading hints only; native extraction and independent review retain
the same eligibility rules. No account names, period-specific people or laws.
"""
import copy
import hashlib
import re
from collections import Counter


def text_key(text):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', str(text)).lower()


def source_hash(row):
    return hashlib.sha256(row.get('content', '').encode()).hexdigest()


def topic_terms(topic, aliases=()):
    names=[*aliases,*re.findall(r'《([^》]+)》',topic),topic]
    out=[]
    for name in names:
        value=text_key(name)
        for word in ('中华人民共和国','国务院','审议通过','讨论','听取','关于',
                     '修改和废止','修改','废止','部分','的决定','修订草案','修正草案',
                     '草案','行动进展情况汇报','进展情况汇报'):
            value=value.replace(word,'')
        if len(value)>=3 and value not in out:out.append(value)
    return out


def reserve_rank(record,topic,aliases):
    body=text_key(record.get('content',''));terms=topic_terms(topic,aliases)
    windows=[]
    for term in terms:
        windows.extend(body[max(0,m.start()-150):m.end()+650]
                       for m in re.finditer(re.escape(term),body))
    # Concrete suggestions near this policy, rather than total article length
    # or arguments about unrelated policies in a long weekly collection.
    actions=('建议','应及时','应当','需要','应对照','防止','容易','须','应关注')
    mechanisms=('台账','依据','衔接','更新','核对','执行','程序','标准','成本',
                '风险','问责','清单','验证','评估','培训','保障','机制')
    reasonings=('意味着','原因','关键','难点','问题','不仅','并非','有利于')
    def score(window):
        return (4*sum(w in window for w in actions)+2*sum(w in window for w in mechanisms)
                +sum(w in window for w in reasonings))
    best=max([score(w) for w in windows]+[0])
    cost=max(500,min(6000,len(body)))**.04
    return best/cost,best,len(windows)


def rank_reserves(records,priority_rows,topic,aliases,completed,*,limit=6,max_chars=60000):
    candidates={r['id'] for r in priority_rows if r.get('decision')=='reserve'
                and topic in str(r.get('topics','')).split('|')}
    done_ids={r['id'] for r in completed};done_text={source_hash(r) for r in completed}
    ranked=[]
    for row in records:
        if row['id'] not in candidates or row['id'] in done_ids or source_hash(row) in done_text:continue
        rank,residual,hits=reserve_rank(row,topic,aliases)
        ranked.append((rank,residual,hits,row))
    ranked.sort(key=lambda r:(-r[0],-r[1],-r[2],len(r[3].get('content','')),r[3]['id']))
    selected=[];seen=set(done_text);characters=0
    for rank,residual,hits,row in ranked:
        body_hash=source_hash(row);size=len(row.get('content',''))
        if body_hash in seen or not size:continue
        if characters+size>max_chars:continue
        selected.append(copy.deepcopy(row));seen.add(body_hash);characters+=size
        if len(selected)>=limit:break
    return selected,{'unread_candidates':len(ranked),'selected_ids':[r['id'] for r in selected],
        'selected_characters':characters,'ranking':'local_policy_argument_hint_not_semantic_approval',
        'selected_scores':[{'id':r['id'],'score':reserve_rank(r,topic,aliases)[1]} for r in selected]}


def rejection_feedback(packet,choices,*,deferred_ids=()):
    """Reuse complete decisions, never reinterpret an unread page as rejected."""
    rejected=[];pending=[];categories=Counter()
    for item in packet['items']:
        if item.get('origin')!='web':continue
        choice=choices.get(item['id'],{});reason=choice.get('reason','')
        row={'id':item['id'],'title':item.get('title',''),'url':item['url'],
             'published_at':choice.get('published_at') or item.get('published_at',''),
             'decision':choice.get('decision'),'reason':reason}
        if (item['id'] in deferred_ids or not item.get('content') or not choice or
                choice.get('classification_origin')=='semantic_reading_deferred'):
            pending.append(row);continue
        if choice.get('decision') not in {'excluded','duplicate'}:continue
        rejected.append(row)
        # Exact recorded codes only. Free-form semantic reasons stay verbatim
        # for the query planner; Python does not decide why an article is bad.
        code=choice.get('classification_origin') or reason.split(':',1)[0]
        if code.startswith(('deterministic_','fixed_')):categories[code]+=1
    return {'completed_rejections':rejected[-24:],'pending_not_negative':pending[-12:],
        'mechanical_codes':dict(categories),'total_completed_rejections':len(rejected),
        'scope':'Original prior reading decisions only; discovery metadata is not a reading result.'}


def query_is_new(query,previous):
    from cwh_host_research import query_format_key
    return query_format_key(query) not in {query_format_key(q) for q in previous}
