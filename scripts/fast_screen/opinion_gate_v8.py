"""Budgeted discovery with exact attributed-utterance coverage and exploration.

Everything outside the queue remains unread reserve. Quote fingerprints are
scheduling evidence, never whole-article or semantic-duplicate certificates.
No historical model labels, personal names or account allowlists are inputs.
"""
from collections import Counter,defaultdict
import math,re,time
from conservative_filter import compact,sentence_records
from refined_filter import DEPLOY,EXTENSION,ROLE
from opinion_gate import evidence,qualifies,MECHANISM,DIAGNOSIS,ATTRIBUTION,FACT_ACTION

VERSION='opinion-gate-9-reading-cost-experimental'
REPORT=re.compile(r'(?:认为|表示|指出|建议|分析|称|说)[，,:：]')
ROLE_END=re.compile(r'教授|研究员|经济学家|学者|分析师|律师|首席|主任|院长|会长|理事长|专家|总监|经理|副总裁|负责人|董事长')
CONDITION=re.compile(r'如果|只有|除非|倘若|前提|条件|一旦|在.{0,20}情况下')

def argument_atom(sentence):
    """Exact core + observed speaker; do not strip a conditional preamble."""
    flat=re.sub(r'\s+','',sentence)
    if FACT_ACTION.search(flat)and not EXTENSION.search(flat)and not ATTRIBUTION.search(flat):return None
    if len(compact(flat))<28:return None
    if not(MECHANISM.search(flat)or DIAGNOSIS.search(flat)or ATTRIBUTION.search(flat)):return None
    m=REPORT.search(flat)
    if m:
        prefix=flat[:m.start()];tail=flat[m.end():].strip('“”\"「」『』。')
        roles=list(ROLE_END.finditer(prefix))
        person=prefix[roles[-1].end():]if roles else re.split('[，,:：。！？!?]',prefix)[-1]
        person=re.sub(r'(?:进一步|同时|也|还|则)$','',person).strip('“”\"「」『』')
        if re.fullmatch(r'[\u4e00-\u9fff]{2,4}',person)and len(compact(tail))>=32 and not CONDITION.search(prefix):
            return {'key':'q:'+person+':'+compact(tail),'kind':'exact_attributed_utterance','speaker_literal':person,
                    'normalized_literal':compact(tail),'raw_sentence':sentence}
    return {'key':'s:'+compact(flat),'kind':'exact_analysis_sentence','speaker_literal':'',
            'normalized_literal':compact(flat),'raw_sentence':sentence}

def local_topics(hit,row,agenda,templates):
    # Official agenda recitation cannot establish analysis-topic coverage.
    residual=[]
    for s in re.split(r'(?<=[。！？!?；;])',hit['text']):
        if FACT_ACTION.search(s)and not EXTENSION.search(s)and not ATTRIBUTION.search(s):continue
        residual.append(compact(s))
    clean=''.join(residual)
    for t in templates:clean=clean.replace(t,'')
    direct=[t for t,aliases in zip(agenda['topics'],agenda['topic_aliases'])if any(compact(w)in clean for w in [t,*aliases])]
    if direct:return direct,'analysis_block_literal'
    # A title is a reading hint only; it never certifies the claim's topic.
    title=compact(row['title'])
    hints=[t for t,aliases in zip(agenda['topics'],agenda['topic_aliases'])if any(compact(w)in title for w in [t,*aliases])]
    if hints:return hints,'title_hint_pending_model'
    # Analysis may use pronouns or introduce its object in an earlier section.
    # Preserve the old local-context hint as an explicitly unverified fallback,
    # rather than treating missing literal topic words as semantic exclusion.
    context=hit.get('topics',[])
    return context,'context_hint_pending_model'if context else'unknown_pending_model'

def select(records,agenda,max_articles=99,max_body_chars=450000,exploration_slots=12,reading_cost_power=.35,exploration_cost_power=0):
    if not 1<=max_articles<=99:raise ValueError('Article budget must be1..99')
    if max_body_chars<1 or exploration_slots<0:raise ValueError('Invalid budget')
    if any(not math.isfinite(n)or not 0<=n<=3 for n in [reading_cost_power,exploration_cost_power]):raise ValueError('Invalid reading-cost power')
    exploration_slots=min(exploration_slots,max_articles)
    start=time.perf_counter();byid={r['id']:r for r in records}
    if len(byid)!=len(records):raise ValueError('Duplicate source IDs')
    df=Counter(n for r in records for n in {n for _,n in sentence_records(r['content'])if len(n)>=18})
    templates=sorted({n for r in records for raw,n in sentence_records(r['content'])if len(n)>=18 and df[n]>=8 and DEPLOY.search(raw)},key=lambda s:(-len(s),s))
    indexes={};features={};rows=[];aliases=defaultdict(set)
    for row in records:
        hits=evidence(row,agenda,templates);atoms={};strong_keys=set();topics=set();strong_topics=set();normalized_body=compact(row['content'])
        for h in hits:
            ht,ht_basis=local_topics(h,row,agenda,templates)
            h.update(legacy_context_topics=h['topics'],topics=ht,topic_basis=ht_basis)
            keys=[]
            for sentence in re.split(r'(?<=[。！？!?；;])',h['text']):
                atom=argument_atom(sentence)
                if atom and atom['normalized_literal']in normalized_body:
                    atoms[atom['key']]=atom;keys.append(atom['key']);aliases[atom['key']].add(row['id'])
            if not keys and len(h['normalized'])>=60 and h['normalized']in normalized_body:
                key='b:'+h['normalized'];keys.append(key)
                atoms[key]={'key':key,'kind':'continuous_block_pending_model','speaker_literal':'',
                            'normalized_literal':h['normalized'],'raw_sentence':h['text']}
                aliases[key].add(row['id'])
            h['atom_keys']=keys
            if ht and keys:
                topics.update(ht)
                if qualifies(h):strong_keys.update(keys);strong_topics.update(ht)
        keys=set(atoms)
        qualified=[h for h in hits if qualifies(h)and h['topics']and h['atom_keys']]
        weak=[h for h in hits if h['topics']and h['atom_keys']and h['score']>=3 and(h['diagnosis']or h['mechanism'])]
        features[row['id']]={'keys':keys,'strong_keys':strong_keys,'topics':strong_topics if qualified else topics,
            'best_score':max((h['score']for h in(qualified or weak)),default=0),'strong':bool(qualified),'weak':bool(weak)and not qualified,
            'atoms':atoms,'actors':{v['speaker_literal']for v in atoms.values()if v['speaker_literal']},'chars':len(row['content'])}
        indexes[row['id']]=hits
        rows.append({'id':row['id'],'title':row['title'],'account':row.get('account',''),'decision':'reserve',
            'reason':'weak_or_uncertain_independent_argument','reading_lane':'','best_score':features[row['id']]['best_score'],
            'qualified_blocks':len(qualified),'topics':'|'.join(sorted(features[row['id']]['topics'])),'body_chars':len(row['content']),
            'exact_utterance_count':sum(v['kind']=='exact_attributed_utterance'for v in atoms.values()),
            'covered_atom_count':0,'argument_atom_count':len(atoms),'representative':'','unread':True})
    audit={r['id']:r for r in rows};covered=set();chosen=[];chosen_ids=set();used=0;topic_counts=Counter();lanes=Counter();seen_actors=set()
    def eligible(id,lane):
        f=features[id]
        return id not in chosen_ids and used+f['chars']<=max_body_chars and bool(f['keys']-covered)and bool(f['topics'])and f['strong'if lane=='strong'else'weak']
    def utility(id,exploratory=False):
        f=features[id];novel=f['keys']-covered
        ratio=len(novel)/max(1,len(f['keys']))
        balance=sum(1/(1+topic_counts[t])for t in f['topics'])
        new_actors=len(f['actors']-seen_actors)
        information=f['best_score']*(.3+.7*ratio)+3*math.sqrt(min(len(novel),12))+7*balance+6*min(new_actors,4)
        # Entire articles are retained; use estimated reading cost to avoid a
        # few very long multi-topic digests exhausting the discovery budget.
        return (information/(1+f['chars']/2500)**(exploration_cost_power if exploratory else reading_cost_power),
                -f['chars'],id)
    def take(id,lane):
        nonlocal used
        f=features[id];chosen.append(byid[id]);chosen_ids.add(id);used+=f['chars'];covered.update(f['keys'])
        topic_counts.update(f['topics']);seen_actors.update(f['actors']);lanes[lane]+=1
        audit[id].update(decision='primary_full_text',reason='budgeted_complete_article_reading',reading_lane=lane)
    # First establish supported discovery coverage; never fill an empty topic
    # with an unrelated article merely to reach a quota.
    floor=min(6,max_articles//max(1,2*len(agenda['topics'])))
    strong_limit=max_articles-exploration_slots
    for _ in range(floor):
        for topic in sorted(agenda['topics'],key=lambda t:(topic_counts[t],agenda['topics'].index(t))):
            if len(chosen)>=strong_limit:break
            if topic_counts[topic]>=_+1:continue
            pool=[id for id in byid if eligible(id,'strong')and topic in features[id]['topics']]
            if pool:take(max(pool,key=utility),'topic_discovery')
    for _ in range(exploration_slots):
        if len(chosen)>=max_articles:break
        pool=[id for id in byid if eligible(id,'weak')]
        if not pool:break
        take(max(pool,key=lambda id:utility(id,exploratory=True)),'weak_signal_exploration')
    while len(chosen)<max_articles:
        pool=[id for id in byid if eligible(id,'strong')]
        if not pool:break
        take(max(pool,key=utility),'strong_argument_backfill')
    for r in rows:
        f=features[r['id']];overlap=f['keys']&covered;r['covered_atom_count']=len(overlap)
        if r['id']in chosen_ids:continue
        reps=sorted({id for key in overlap for id in aliases[key] if id in chosen_ids})
        r['representative']='|'.join(reps)
        if f['keys']and not(f['keys']-covered):r['reason']='indexed_arguments_represented_other_text_unread'
        elif f['strong']or f['weak']:r['reason']='candidate_over_budget_or_lower_priority'
    quote_clusters=[{'speaker_literal':key.split(':',2)[1],'normalized_literal':key.split(':',2)[2],
                    'source_ids':sorted(ids),'selected_source_ids':sorted(ids&chosen_ids),
                    'status':'exact_quote_scheduling_alias_not_article_approval'}
        for key,ids in aliases.items()if key.startswith('q:')and len(ids)>1]
    summary={'policy':VERSION,'input_articles':len(records),'primary_articles':len(chosen),'primary_body_chars':used,
        'priority_limits':{'articles':max_articles,'body_characters':max_body_chars,'weak_signal_slots':exploration_slots,
                          'reading_cost_power':reading_cost_power,'exploration_cost_power':exploration_cost_power},
        'reading_lanes':dict(lanes),'reserve_articles':len(records)-len(chosen),
        'reserve_reasons':dict(Counter(r['reason']for r in rows if r['decision']=='reserve')),
        'script_topic_hints_not_semantic_coverage':dict(topic_counts),'exact_quote_clusters':len(quote_clusters),
        'script_seconds':round(time.perf_counter()-start,3),
        'note':'All reserves remain unread; exact quote aliases do not prove whole-article equivalence. Complete exported bodies unchanged. No semantic labels used.'}
    return chosen,rows,summary,{'article_evidence':indexes,'exact_quote_clusters':quote_clusters}
