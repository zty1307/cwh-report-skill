"""Deterministic current-attribution guards; never decide an article is useless."""
import argparse,re
from datetime import date
from pathlib import Path
from collections import Counter
from portable_screen import load,save,digest

EVENT=re.compile(r'(?:(?:\d{4}年)?\d{1,2}月\d{1,2}日|本次|本期|此次)?(?:国务院常务会议|国务院常务会|国常会|会议)')
GENERIC={'专家','受访专家','相关专家','业内人士','受访者','有关人士','相关人士','分析人士','某专家','研究组','课题组','本刊研究组','本刊编辑部'}
DATED=re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')

def date_context_flags(v,window_start):
    # A dated context is a reason to verify the speaker's original statement,
    # not proof that the claim itself is old. Do not substitute the repost date.
    if v.get('kind')not in {'person','joint_people','institution'}or not window_start:return[]
    start=date.fromisoformat(window_start[:10]);flags=[];seen=set()
    for field in ['excerpt','role_excerpt']:
        text=v.get(field,'')
        for m in DATED.finditer(text):
            try:day=date(*map(int,m.groups()))
            except ValueError:continue
            if day>=start or day.isoformat()in seen:continue
            seen.add(day.isoformat());flags.append({'context_date':day.isoformat(),'evidence_field':field,
                'literal_date':m.group(),'context':text[max(0,m.start()-60):m.end()+160],
                'reason':'earlier_dated_context_requires_statement_binding','automatic_exclusion':False})
    return flags

def reason(v):
    name=re.sub(r'\s+','',v.get('name',''))
    if v.get('kind')!='account'and EVENT.fullmatch(name):return'meeting_statement_is_not_external_opinion'
    if v.get('kind')in {'person','joint_people','institution'}and name in GENERIC:return'current_speaker_label_is_not_identifiable'
    return''

def apply(case):
    source=case
    if(case/'completion_pointer.json').exists():source=Path(load(case/'completion_pointer.json')['recovery_directory'])
    path=source/'results/nominations_pending_review.json';rows=load(path);eligible=[];returned=[]
    agenda=load(source/'model/agenda.json');sources={r['id']:r for r in load(source/'model/sources.json')}
    for v in rows:
        code=reason(v)
        if code:
            returned.append({**v,'original_unreviewed_report_sentence':v.get('report_sentence',''),'report_sentence':'',
                'script_guard_reason':code,'script_disposition':'return_to_event_material_or_attribution_repair',
                'whole_article_excluded':False,'formal_ready':False})
        else:eligible.append({**v,'script_disposition':'pending_independent_review','formal_ready':False,
            'time_context_flags':date_context_flags(v,agenda.get('window_start',''))})
    out=case/'results_guarded';save(out/'candidates_pending_independent_review.json',eligible)
    save(out/'returned_to_event_material_or_attribution_repair.json',returned)
    result={'input_nominations':len(rows),'pending_independent_review':len(eligible),'returned_current_attributions':len(returned),
        'return_reasons':dict(Counter(v['script_guard_reason']for v in returned)),
        'original_candidate_file':str(path.resolve()),'original_candidates_hash':digest(rows),
        'guard_code_hash':digest(Path(__file__).read_text('utf-8')),'whole_articles_excluded':0,'semantic_approval':False,'formal_ready':0}
    result['earlier_date_context_needs_verification']=sum(bool(v['time_context_flags'])for v in eligible)
    save(out/'summary.json',result)
    topics=load(source/'model/agenda.json')['topics'];lines=['脚本检查后的初筛候选：仍须独立复核及原始网页、身份、原发时间核验。',
        '会议自身话语、无法指认的当前主体已退回待处理区；原文及观点内容保留，未据此否定整篇文章。','']
    for topic in topics:
        vals=[v for v in eligible if v['topic']==topic];lines.extend([f'{topic}（待复核{len(vals)}条）',''])
        for v in vals:
            r=sources[v['id']]
            lines.extend([v.get('report_sentence')or f"【身份或字段待核】{v.get('name','')}：{v['claim']}",
                f"编号：{v['candidate_id']}；状态：待独立复核"+('；存在早于本期的日期上下文，须核发言归属'if v['time_context_flags']else''),
                f"原文标题：{r['title']}；监测时间：{r.get('published_at','')}（非原发时间认证）",f"监测链接：{r.get('url','')}",''])
    out.joinpath('分议题候选_脚本检查后_待复核.txt').write_text('\n'.join(lines),encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);a=p.parse_args();print(apply(a.case))
