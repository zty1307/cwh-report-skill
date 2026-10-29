"""Recover already-reviewed claims blocked solely by name layout whitespace.

Diagnostic postprocessing only: frozen benchmark artifacts stay unchanged.
No semantic fields, source text, offsets, dates or review decisions are edited.
"""
import argparse,copy,hashlib,json,re
from pathlib import Path
from portable_screen import load,save,digest,segments,resolve_range

def recover(row,view):
    if view.get('independent_decision')!='retain' or view.get('kind')not in {'person','joint_people'}:
        return None
    if set(view.get('errors',[]))!={'identity_name_not_in_anchor'}:return None
    if not view.get('role') or not view.get('identity'):return None
    if hashlib.sha256(row['content'].encode('utf-8')).hexdigest()!=view.get('source_sha256'):
        raise ValueError('Source hash changed')
    a,b=resolve_range(view['identity'],segments(row));anchor=row['content'][a:b]
    if view.get('role_excerpt')!=anchor:raise ValueError('Identity anchor changed')
    names=[n.strip()for n in re.split('[、，,]',view['name'])if n.strip()]
    compact=lambda s:re.sub(r'\s+','',s)
    if not names or not all(compact(n) in compact(anchor)for n in names):return None
    if view['kind']=='joint_people' and not all(n in view['role']for n in names):return None
    result=copy.deepcopy(view);result['errors']=[]
    prefix=view['role'] if view['kind']=='joint_people' or view['role'].endswith(view['name']) else view['role']+view['name']
    result['report_sentence']=prefix+'认为，'+view['claim'].strip().rstrip('。')+'。'
    result.update(status='candidate_pending_original_web_source',formal_ready=False,
       mechanical_recovery={'type':'identity_whitespace_only','previous_candidate_hash':digest(view),
                            'previous_errors':view['errors'],'semantic_review_reused':True,
                            'note':'Only literal identity matching ignores layout whitespace; all semantic fields and raw source remain unchanged.'})
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--review',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('Fresh recovery directory required')
    sources={r['id']:r for r in load(a.review/'sources.json')};views=load(a.review/'reviewed_candidates.json')
    recovered=[]
    for v in views:
        new=recover(sources[v['id']],v)
        if new:recovered.append(new)
    qualified=load(a.review/'source_check_candidates.json')
    if set(v['candidate_id']for v in qualified)&set(v['candidate_id']for v in recovered):raise ValueError('Already-qualified candidate recovered twice')
    save(a.out/'recovered_candidates.json',recovered)
    save(a.out/'all_source_check_candidates.json',qualified+recovered)
    save(a.out/'summary.json',{'frozen_test_candidates':len(qualified),'whitespace_recoveries':len(recovered),
                             'candidate_pool_after_repair':len(qualified)+len(recovered),'formal_ready':0,
                             'frozen_test_rewritten':False,'semantic_fields_changed':False})
    (a.out/'空白排版修复补回观点.txt').write_text('原测试计数不变；以下只修复身份锚点中的姓名排版空白，复用已有独立retain，仍待溯源。\n\n'+
        '\n\n'.join(v['candidate_id']+' '+v['report_sentence']for v in recovered),encoding='utf-8')
    print(json.dumps(load(a.out/'summary.json'),ensure_ascii=False))

if __name__=='__main__':main()
