"""Second deterministic gate. No historical AI labels participate in decisions.

Inspect every sentence; never discard an article by its title, account or length.
The audit records evidence spans, so rules can be inspected on another period.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import time
from collections import Counter
from pathlib import Path
from conservative_filter import compact, sentence_records, filter_records, csv_write

VERSION = "refined-8"
# These identify text functions, not the names of current office holders.
DEPLOY = re.compile(r"^(?:会议(?:指出|强调|要求|听取|审议|研究)|要|进一步提高|国务院总理|中共中央|新华社.{0,18}电)")
OFFICIAL = re.compile(r"^(?:.{0,22})?(?:会议|国常会|会商)(?:指出|强调|要求|听取|审议|研究|提出)|^(?:他|她)强调")
EXTENSION = re.compile(r"意味着|表明|反映出|我们认为|笔者|我认为|这说明|不难看出|换句话说|本质上")
FOOTER = re.compile(r"免责声明|不构成.{0,15}投资建议|市场有风险|投资[需须]谨慎|版权归|侵权.{0,15}删除|扫码|关注公众号|点击.{0,12}关注|责任编辑|编辑[：:]|校对[：:]|审核[：:]|作者简介[：:]|仅供参考|不承担.{0,20}责任")
TRADE = re.compile(r"涨停|跌停|买入|卖出|仓位|短线|低吸|打板|止盈|止损|追涨|抄底|减仓|加仓|荐股|个股|大盘|主力资金|板块轮动|股价|股市|沪指|深成指|创业板指|标的|估值|行情|盘面|收盘|A股|a股|反弹|看涨|看跌|牛市|熊市|K线|k线|技术面")
TRADING_TITLE = re.compile(r"A股|股市|复盘|早盘|午评|收评|晚评|龙虎榜|行情|投资策略|后市|涨停|盘前|看盘|股民")
ROLE = re.compile(r"教授|研究员|经济学家|学者|分析师|律师|评论员|智库|课题组|研究组|研究院|研究所|首席|副会长|院长")
SPEECH = re.compile(r"认为|指出|表示|建议|分析|强调|提出|说[：，]|给出.{0,10}分析")
# Structural arguments are broader than expert speech, so account-authored
# analysis and diagnosis without a proposal are eligible for full reading.
ARGUMENT = re.compile(r"根源|难点|瓶颈|短板|制约|风险|问题|背后|逻辑|矛盾|不足|不够|取决于|并非|而是|不能|不应|才能|亟[须需]|痛点|堵点|重复建设|过度|闲置|为何|为什么|因为|由于|导致|从而|有助于|有利于|降低.{0,18}成本|提升.{0,18}效率|相互关联|相互依赖|系统集成|协同|失衡|错配|失效|可靠性|干扰|门槛|脱节|割裂|碎片化|不再.{0,20}而|决定了|不仅.{0,30}(?:更|还)|意味着|本质|既.{0,25}又|需要|应当|必须|建议|乘数效应")
SPECIFIC = re.compile(r"根源|瓶颈|制约|风险|问题|矛盾|不足|不够|取决于|并非|而是|不能|不应|才能|亟须|痛点|堵点|重复建设|过度|闲置|为何|为什么|因为|由于|导致|从而|降低.{0,18}成本|提升.{0,18}效率|相互关联|相互依赖|系统集成|失衡|错配|失效|可靠性|干扰|门槛|脱节|割裂|碎片化|不再.{0,20}而|本质|意味着")
PUBLIC_ISSUE = re.compile(r"监管|制度|规则|标准|产权|公共|跨域|跨区|区域|治理|确权|授权|合规|安全|成本|效率|供需|需求|供给|技术|生态|产业链|资源|基础设施|服务|财政|融资|资金|人才|场景|研发|创新|装备|救援|预警|群众|社区|城乡|设施|能源|电力|用电|能耗|用地|土地|空间|联运|运输|物流|数据|算力|通信|健身|体育|健康|运力|时刻|旅客|航线")
DIAGNOSTIC = re.compile(r"根源|难点|瓶颈|短板|制约|矛盾|不足|不够|取决于|并非|而是|不能|不应|才能|亟[须需]|痛点|堵点|重复建设|过度|闲置|为何|为什么|因为|由于|导致|从而|降低.{0,18}成本|提升.{0,18}效率|相互关联|相互依赖|系统集成|失衡|错配|失效|可靠性|干扰|门槛|脱节|割裂|碎片化|不再.{0,20}而|本质|意味着|乘数效应")
SIGNED_RESEARCH=re.compile(r'(?:本报告分析师|报告作者|作者|撰文)[：:]\s*[\u4e00-\u9fff]{2,12}')
STRUCTURAL = re.compile(r"监管|制度|规则|标准|产权|跨域|跨区|协同|确权|授权|合规|审查|责任|信息孤岛|条块分割|碎片化|错配|同质化|卡脖子|自主可控|利用率|能耗|用电|电力|闲置|资本支出|研发投入|封闭|开放生态|软硬件|人才|适航|技术路线|供需|商业化|真实需求|技术突破|技术瓶颈|关键瓶颈|制约")


def features(row, aliases, templates):
    # Export line wraps are formatting, not sentence or paragraph boundaries.
    parts = [(s.strip(),compact(s)) for s in re.split(r'[。！？!?；;]+',row['content']) if compact(s)]
    cleaned = []
    for raw, norm in parts:
        for template in templates:
            if template in norm:
                norm = norm.replace(template, " " * len(template))
        if FOOTER.search(raw) and len(norm) < 350 and not (ROLE.search(raw) and SPEECH.search(raw) and SPECIFIC.search(raw)):
            norm = ""
        if OFFICIAL.search(raw) and not EXTENSION.search(raw) and not (ROLE.search(raw) and SPEECH.search(raw)):
            norm = ""
        cleaned.append(norm.strip())
    evidence, attributed, trade_analysis = [], [], []
    full_normalized = compact(row['content'])
    offsets=[]
    cursor=0
    for _,norm in parts:
        at=full_normalized.find(norm,cursor)
        offsets.append(at)
        cursor=max(cursor,at+len(norm))
    global_arguments=[]
    for i, norm in enumerate(cleaned):
        if len(norm) < 20:
            continue
        # One nearby sentence only supplies the topic/identity; the qualifying
        # judgment must itself be in this unmasked sentence.
        nearby = "".join(cleaned[max(0, i-1):i+2])
        at=offsets[i]
        context=full_normalized[max(0,at-160):at+len(parts[i][1])+260]
        topic = any(term in context for term in aliases)
        has_arg = bool(ARGUMENT.search(norm))
        has_speech = bool(ROLE.search(norm) and SPEECH.search(norm) and has_arg)
        trade = bool(TRADE.search(norm))
        # Several nontrading structural arguments in a long digest deserve
        # semantic review even if the agenda term occurs in its section title.
        if not trade and DIAGNOSTIC.search(norm) and PUBLIC_ISSUE.search(norm):
            global_arguments.append(parts[i][0])
        if not topic:
            continue
        if has_speech and not trade:
            attributed.append(parts[i][0])
        if has_arg and PUBLIC_ISSUE.search(norm):
            if not trade and (DIAGNOSTIC.search(norm) or has_speech):
                evidence.append(parts[i][0])
            elif trade:
                trade_analysis.append(parts[i][0])
    trades = sum(len(TRADE.findall(s)) for s in cleaned)
    structural=[s for s in evidence if STRUCTURAL.search(compact(s)) and DIAGNOSTIC.search(compact(s))]
    return {"independent_contexts": len(evidence), "attributed_contexts": len(attributed),
            "trade_contexts": len(trade_analysis), "trade_hits": trades,
            "trade_title": bool(TRADING_TITLE.search(row["title"])),
            "global_arguments":global_arguments,
            "global_structural_contexts":sum(bool(STRUCTURAL.search(compact(s))) for s in global_arguments),
            "structural_contexts":len(structural),
            "evidence": evidence[:6], "attributed_evidence": attributed[:3],
            "residual_chars": sum(len(s) for s in cleaned)}


def refine(records, agenda):
    started = time.perf_counter()
    # Run first gate with its audited provenance; no labels imported here.
    stage1, audits, base = filter_records(records, agenda, deployment_pattern=DEPLOY)
    base['deployment_pattern']='generic_roles_without_incumbent_names'
    df = Counter(n for r in records for n in {n for _, n in sentence_records(r['content']) if len(n)>=18})
    templates = sorted({n for r in records for raw,n in sentence_records(r['content'])
                        if len(n)>=18 and df[n]>=8 and DEPLOY.search(raw)}, key=len, reverse=True)
    aliases = {compact(s) for topic, extra in zip(agenda['topics'], agenda['topic_aliases'])
               for s in [topic,re.sub(r'（.*?）','',topic),*extra] if s}
    byid = {a['id']:a for a in audits}
    kept=[]
    for r in stage1:
        f=features(r,aliases,templates)
        reason=''
        global_protection=(len(f['global_arguments'])>=3 or
                           (len(f['global_arguments'])>=2 and SIGNED_RESEARCH.search(r['content']))) and bool(byid[r['id']]['topics'])
        global_protection=bool(global_protection)
        if not f['independent_contexts'] and not f['attributed_contexts'] and not global_protection:
            reason = 'only_trading_topic_arguments' if f['trade_contexts'] else 'no_residual_topic_argument'
        # A trading article with a residual nontrading argument remains for
        # semantic review. A frozen audit found a real capital-expenditure
        # argument inside this category; article-wide trade intent is unsafe.
        byid[r['id']].update(refined_reason=reason, independent_contexts=f['independent_contexts'],
            attributed_contexts=f['attributed_contexts'], trade_hits=f['trade_hits'],
            evidence=json.dumps(f['evidence'],ensure_ascii=False),
            attributed_evidence=json.dumps(f['attributed_evidence'],ensure_ascii=False),
            global_argument_protection=global_protection,
            structural_contexts=f['structural_contexts'],
            global_argument_evidence=json.dumps(f['global_arguments'][:4],ensure_ascii=False))
        if reason:
            byid[r['id']].update(decision='exclude',reason=reason)
        else: kept.append(r)
    # Fixed columns, including first-gate exclusions.
    for a in audits:
        for k in ('refined_reason','independent_contexts','attributed_contexts','trade_hits','evidence','attributed_evidence','global_argument_protection','global_argument_evidence','structural_contexts'):
            a.setdefault(k,'')
    return kept,audits,{'policy':VERSION,'first_gate':base,'input_rows':len(records),'remaining_articles':len(kept),
        'remaining_full_text_characters':sum(len(r['content']) for r in kept),
        'additional_exclusions':dict(Counter(a['refined_reason'] for a in audits if a['refined_reason'])),
        'script_seconds':round(time.perf_counter()-started,3)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--records',type=Path,required=True);p.add_argument('--agenda',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();rows=json.loads(a.records.read_text(encoding='utf-8'));agenda=json.loads(a.agenda.read_text(encoding='utf-8'))
    kept,audit,summary=refine(rows,agenda);a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'remaining_records.json').write_text(json.dumps(kept,ensure_ascii=False,indent=2),encoding='utf-8')
    csv_write(a.out/'filter_audit.csv',audit)
    (a.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
