"""Precision-oriented, evidence-indexed queue. No model labels at runtime.

The priority budget is disclosed; overflow is unread reserve, never a semantic
rejection. Every promoted source keeps its complete, unchanged exported body.
"""
from __future__ import annotations
import argparse,json,re,time,csv,hashlib,math
from pathlib import Path
from collections import Counter,defaultdict
from conservative_filter import compact,csv_write,sentence_records
from refined_filter import refine,DEPLOY,FOOTER,OFFICIAL,EXTENSION,ROLE,SPEECH,TRADE

VERSION='opinion-gate-6-experimental'
MECHANISM=re.compile(r'因为|由于|导致|使得|从而|取决于|根源|关键在|本质|意味着|正因|只有.{0,50}才|通过.{0,45}(?:降低|减少|提高|提升|解决|保障)|相互关联|相互依赖|相互联系|系统集成|不再.{0,25}而|并非.{0,25}而|不仅.{0,40}(?:更|还)|反向|倒逼|才能|造成|难以|无法|越.{0,12}越|以免|否则|协同|依赖|需要|有助于|有利于|降低|提高|提升|决定|乘数效应|带动')
MECHANISM=re.compile(MECHANISM.pattern+r'|不在.{0,25}而在|并不.{0,30}而|而是|影响|如果.{0,70}(?:就|则)|只要.{0,40}就|因而|因此|因果|受.{0,30}制约')
DIAGNOSIS=re.compile(r'瓶颈|短板|堵点|痛点|壁垒|门槛|失衡|错配|脱节|割裂|碎片化|同质化|重复建设|闲置|利用率|产能过剩|分布不均|不均衡|供给不足|不完善|不充分|供给不足|不匹配|不足|不够|制约|缺口|缺乏|成本过高|成本高|高成本|安全隐患|责任不清|归属不明|依赖进口|薄弱|卡脖子|标准不一|通而不畅|无序|垄断|一刀切|收割|侵蚀|刚性|融资成本|高利率|脆弱|风险阈值|亟[需须]|条块分割|资源浪费|过度投资')
GOVERNANCE=re.compile(r'制度|机制|监管|治理|标准|产权|确权|授权|合规|责任|审查|审批|认证|适航|公共|跨区域|跨地区|跨域|区域|全国统一|分工|基础设施|资源配置|需求匹配|资源整合|产业链|供应链|应用场景|科研|研发|原创|技术路线|转化|普惠|基层|社区|城乡|场地|校园|医保|财政|救援|演练|预警|安全韧性|土地|用地|立法|生态|电网|能耗|用电|自主可控|国产替代')
GOVERNANCE=re.compile(GOVERNANCE.pattern+r'|支付|缴存|提取|医疗|住房|就业|供电|资本开支|互联互通|智能调度|航线|时刻|旅客|数字基建|体育参与|空域|临床路径|防护|隐患|社会经济条件')
TOOL=re.compile(r'建议|应当|亟[须需]|需要|不能|不应|必须|可通过|应(?:建立|完善|加强|推动|优化|采用|防止|避免|依据|依托)|分类|分级|差异化|因地制宜|分阶段|错位发展|沙盒|首台套|无预案|平台接入|留痕|追溯|预警叫应|全链条|协同调度|系统集成|成本分担|社会资本|保险|标准统一|统一标准|认证|权责|产权')
CONCRETE=re.compile(r'成本|效率|资金|电力|能耗|需求|供给|利用率|投入|风险|安全|数据|场地|空间|家庭|资源|企业|地方|学校|社区|群众|制造|转化|融资|利润|研发|技术|运输|航线|运力|时刻|维护|责任|权益|预警|救援|支出|缴存|提取|贷款|住房|就业|消费|投资|产能|资本|收入|人才|网络')
CONCRETE=re.compile(CONCRETE.pattern+r'|医疗|体育|支付|机架|芯片|服务器|电价|电池|电机|飞控|飞机|停机坪|防洪|玻璃|门窗|树木|诊疗|处方|基站|光计算|全覆盖|上架率|温控|冷链|装卸|货场|铁路|公路|航班|城市|经济账')
ATTRIBUTION=re.compile(r'(?:教授|研究员|经济学家|学者|分析师|律师|首席|主任|院长|会长|理事长).{0,35}(?:认为|表示|指出|分析|建议|强调|给出)|(?:报告|研报|研究|证券|智库|机构).{0,20}(?:认为|指出|建议|发现)|(?:文|作者|撰文|本报告分析师)[/：:]')
COMMENTARY=re.compile(r'点评|评论|解读|观察|笔者|我们认为|我认为|换句话说|说白了|值得注意|这说明|本质|根源|为什么|并非|不是.{0,20}而|问题在于|关键在于')
FACT_ACTION=re.compile(r'^(?:.{0,25})?(?:会议|国常会|会商)(?:指出|强调|要求|听取|审议|研究|提出)|^(?:要|通知要求|规划提出|方案要求|文件要求|办法规定|条例规定|国家要求)')
MARKET_RESULT=re.compile(r'股价|涨停|跌停|估值|买入|卖出|仓位|短线|低吸|打板|止盈|止损|追涨|抄底|减仓|加仓|荐股|个股|大盘|主力资金|盘面|收盘|A股|a股|反弹|看涨|看跌|牛市|熊市|K线|k线|业绩|利润增|营收|龙头|受益标的|资金流向|板块')
HEALTH_HOWTO=re.compile(r'肌肉|肌群|心率|蛋白|抗阻|有氧|血糖|代谢|脂肪|睡眠|饮食|减肥|减脂|每周.{0,8}次|每次.{0,8}分钟|健身动作|运动处方')

def units(text):
    # Blank lines distinguish digest entries, while single wrapped lines in
    # names/phrases do not become independent evidence.
    out=[]
    for m in re.finditer(r'[^。！？!?；;]+(?:[。！？!?；;]|$)',text):
        for s in re.split(r'\n\s*\n',m.group()):
            s=s.strip()
            if compact(s):out.append((s,compact(s)))
    # Reasons/conditions are often in the next short sentence. Coalesce whole
    # sentences into small, continuous analysis blocks; no text is truncated.
    blocks=[];raws=[];size=0
    for raw,norm in out:
        raws.append(raw);size+=len(norm)
        if size>=160:
            joined=''.join(raws);blocks.append((joined,compact(joined)));raws=[];size=0
    if raws:
        joined=''.join(raws);blocks.append((joined,compact(joined)))
    return blocks

def evidence(row,agenda,templates):
    parts=units(row['content']);flat=compact(row['content']);all_alias={compact(w) for t,ws in zip(agenda['topics'],agenda['topic_aliases'])for w in [t,*ws]}
    hits=[];cursor=0
    for i,(raw,norm)in enumerate(parts):
        at=flat.find(norm,cursor)
        if at<0:at=flat.find(norm)
        cursor=max(cursor,at+len(norm))
        if FOOTER.search(raw)and len(norm)<350 and not ATTRIBUTION.search(raw):continue
        cleaned=norm
        for t in templates:
            if t in cleaned:cleaned=cleaned.replace(t,' '*len(t))
        if not cleaned.strip():continue
        # Only erase the deployment sentence itself, not an adjacent original
        # analysis that happens to follow it in the same block.
        residual=[]
        for sentence in re.split(r'(?<=[。！？!?；;])',raw):
            n=compact(sentence)
            if FACT_ACTION.search(sentence)and not EXTENSION.search(n)and not ATTRIBUTION.search(n):continue
            residual.append(n)
        cleaned=''.join(residual)
        for t in templates:cleaned=cleaned.replace(t,' ' * len(t))
        context=flat[max(0,at-500):at+len(norm)+500]
        topics=[t for t,aliases in zip(agenda['topics'],agenda['topic_aliases'])if any(compact(a)in context for a in [t,*aliases])]
        near=flat[max(0,at-650):at+len(norm)+200]
        # The argument itself must contain analytical substance. Neighbours
        # supply attribution/topic only, never manufacture a causal judgment.
        diag=len(set(DIAGNOSIS.findall(cleaned)));mech=len(set(MECHANISM.findall(cleaned)));gov=len(set(GOVERNANCE.findall(cleaned)));tool=len(set(TOOL.findall(cleaned)));detail=len(set(CONCRETE.findall(cleaned)))
        attributed=bool(ATTRIBUTION.search(cleaned)or((ROLE.search(near)or ATTRIBUTION.search(near))and SPEECH.search(cleaned))or re.search(r'研究.{0,4}(?:发现|指出|表明|揭示)|结果表明',cleaned))
        authored=bool(COMMENTARY.search(cleaned))
        trade=len(MARKET_RESULT.findall(cleaned));health=len(HEALTH_HOWTO.findall(cleaned))
        if not topics:
            # A section can introduce the policy object long before its
            # argument. This is a protected reserve rather than a false no.
            if not any(a in flat for a in all_alias):continue
        if len(cleaned)<32 or detail<1:continue
        policy_argument=(detail>=2 or (diag>=2 and gov>=2) or (attributed and detail>=1 and gov>=1)) and (diag>=1 or mech>=1 or (attributed and tool>=1)) and (gov>=1 or attributed or (topics and (diag or mech>=2)))
        if not policy_argument:continue
        if trade and not(gov>=2 and (diag>=1 or mech>=2)):continue
        if health>=2 and not re.search(r'公共|财政|医保|学校|校园|社区|城乡|场地|设施|资源配置',cleaned):continue
        score=3*bool(topics)+min(diag,2)*2+min(mech,2)+min(gov,3)+min(tool,1)+4*attributed+authored-min(trade,3)*2
        # Meaningful context, exact raw evidence and all source text remain
        # available; the score is a priority signal, never semantic approval.
        keys={compact(s)for s in re.split('[。！？!?；;]',raw)if len(compact(s))>=25 and (MECHANISM.search(compact(s))or DIAGNOSIS.search(compact(s))or ATTRIBUTION.search(compact(s)))}
        hits.append({'text':raw,'normalized':norm,'argument_keys':sorted(keys or {norm}),'topics':topics,'score':score,'diagnosis':diag,'mechanism':mech,'governance':gov,'tool':tool,'attributed':attributed,'trade':trade,'position':at})
    return hits

def qualifies(h):
    return bool(h['score']>=7 and (h['attributed'] or h['diagnosis']>=2 or (h['diagnosis']>=1 and h['mechanism']>=1) or (h['mechanism']>=2 and h['governance']>=2)))

def select(records,agenda,max_articles=99,max_body_chars=650000):
    if not 1<=max_articles<=99:raise ValueError('This experimental reading queue is limited to 1..99 articles')
    if max_body_chars<1:raise ValueError('Body character budget must be positive')
    start=time.perf_counter();df=Counter(n for r in records for n in {n for _,n in sentence_records(r['content'])if len(n)>=18})
    templates=sorted({n for r in records for raw,n in sentence_records(r['content'])if len(n)>=18 and df[n]>=8 and DEPLOY.search(raw)},key=lambda v:(-len(v),v))
    indexes={r['id']:evidence(r,agenda,templates)for r in records};rows=[]
    for r in records:
        hits=indexes[r['id']];qualified=[h for h in hits if qualifies(h)]
        topics=sorted({t for h in qualified for t in h['topics']})
        rows.append({'id':r['id'],'title':r['title'],'account':r.get('account',''),'decision':'reserve','reason':'weak_or_uncertain_independent_argument',
            'best_score':max((h['score']for h in hits),default=0),'qualified_blocks':len(qualified),'topics':'|'.join(topics),'body_chars':len(r['content']),
            'evidence':json.dumps(qualified[:8],ensure_ascii=False),'representative':'','unread':True})
    byid={r['id']:r for r in records};audit={r['id']:r for r in rows}
    eligible=[r for r in rows if r['qualified_blocks']]
    # Greedy coverage uses exact qualifying argument strings. Repeated names,
    # titles, high similarity and author quotas never establish duplication.
    chosen=[];covered=set();used=0;topic_counts=Counter()
    pending={r['id']for r in eligible}
    while pending and len(chosen)<max_articles:
        candidates=[]
        for id in pending:
            r=audit[id];hs=[h for h in indexes[id]if qualifies(h)]
            novel=[h for h in hs if set(h['argument_keys'])-covered]
            if not novel:continue
            n=len(byid[id]['content'])
            if used+n>max_body_chars:continue
            balance=sum(1/(1+topic_counts[t])for t in {t for h in novel for t in h['topics']})
            # Cover distinct arguments first. A long article with several
            # concrete arguments must not lose solely to short filler.
            novel_count=len(set.union(*(set(h['argument_keys'])-covered for h in novel)))
            utility=max(h['score']for h in novel)+4*math.sqrt(min(novel_count,12))+balance*2-n/6000
            candidates.append((utility,-n,id,novel))
        if not candidates:break
        _,_,id,novel=max(candidates);pending.remove(id);chosen.append(byid[id]);used+=len(byid[id]['content'])
        covered.update(k for h in indexes[id]if qualifies(h)for k in h['argument_keys']);topic_counts.update({t for h in novel for t in h['topics']});audit[id].update(decision='primary_full_text',reason='specific_policy_argument_with_novel_evidence',unread=True)
    chosen_normalized={s['id']:compact(s['content'])for s in chosen}
    for r in eligible:
        if r['decision']=='primary_full_text':continue
        hs=[h for h in indexes[r['id']]if qualifies(h)]
        if hs and all(set(h['argument_keys'])<=covered for h in hs):
            representatives=[s['id']for s in chosen if any(k in chosen_normalized[s['id']]for h in hs for k in h['argument_keys'])]
            r.update(reason='qualifying_arguments_represented_in_primary',representative='|'.join(representatives))
        else:r['reason']='candidate_over_budget_or_lower_priority'
    summary={'policy':VERSION,'input_articles':len(records),'primary_articles':len(chosen),'primary_body_chars':used,'priority_limits':{'articles':max_articles,'body_characters':max_body_chars},
        'reserve_articles':len(records)-len(chosen),'reserve_reasons':dict(Counter(r['reason']for r in rows if r['decision']=='reserve')),
        'topic_coverage':dict(topic_counts),'script_seconds':round(time.perf_counter()-start,3),'note':'Reserve is unread, not semantically rejected. Hard budget is disclosed; no zero-miss claim. No historical decisions used by this selector.'}
    return chosen,rows,summary,indexes

def main():
    p=argparse.ArgumentParser();p.add_argument('--records',type=Path,required=True);p.add_argument('--agenda',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--max-articles',type=int,default=99);p.add_argument('--max-body-chars',type=int,default=650000);a=p.parse_args()
    records=json.loads(a.records.read_text(encoding='utf-8'));agenda=json.loads(a.agenda.read_text(encoding='utf-8'));selected,audit,summary,index=select(records,agenda,a.max_articles,a.max_body_chars)
    a.out.mkdir(parents=True,exist_ok=True)
    for name,v in [('primary_records.json',selected),('summary.json',summary),('evidence_index.json',index)]: (a.out/name).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
    csv_write(a.out/'filter_audit.csv',audit);print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
