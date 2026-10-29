"""Automatic bounded supplementation after primary research; keep verified fallback."""
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import time
import uuid
import csv
from pathlib import Path

from cwh_pipeline_runtime import atomic_write_json
from cwh_prepared_research import digest
from cwh_host_research import HostModelError, SemanticResponseError, collect_topic
from cwh_article_reading import reading_prompt
from cwh_article_read_cache import key as reading_key, load as load_reading, store as save_reading, proofs
from cwh_author_batches import partition_author_packet, synthesis_packet, native_topic_synthesis
from cwh_semantic_compiler import make_packet, compile_topic
from cwh_semantic_recovery import interruption, defer_reading
from cwh_feedback_recall import rank_reserves, rejection_feedback, query_is_new
from cwh_raw_recall_collection import collect_subset


def read(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def body_claims(bundle):
    return [(t['topic'], e) for t in bundle['viewpoints']['by_topic']
            for c in t.get('clusters', []) for e in c.get('evidence', [])]


def query_values(result):
    """Normalize explicit query slots only; keep every executed string literal."""
    rows=result.get('items')
    if not isinstance(rows,list) or not rows:return None
    out=[]
    for row in rows:
        if not isinstance(row,dict) or not row:return None
        slots=[]
        for name,value in row.items():
            match=re.fullmatch(r'query(?:_([1-9]\d*))?',name)
            if not match or not isinstance(value,str):return None
            slots.append((int(match.group(1) or 1),value))
        if len({n for n,_ in slots})!=len(slots):return None
        out.extend(value for _,value in sorted(slots))
    return out


def deadlines(started, contract, policy):
    end = started + contract['research_deadline_seconds'] - 15
    synthesis_end = end - policy['independent_review_reserve_seconds']
    return synthesis_end - policy['synthesis_reserve_seconds'], synthesis_end, end


def operation_workspace(root,operation_key):
    # Long inherited run names plus64hex directories exceed Win32 MAX_PATH.
    # Keep the full identity inside the short directory to reject collisions.
    path=Path(root)/operation_key[:16]
    path.mkdir(parents=True,exist_ok=True)
    identity=path/'identity.json'
    if identity.exists() and read(identity)['key']!=operation_key:
        raise ValueError('Short operation directory collision')
    if not identity.exists():atomic_write_json(identity,{'key':operation_key})
    return path


def effective_bundle(job):
    receipt = Path(job) / 'artifacts/remaining_research_receipt.json'
    if receipt.is_file():
        r = read(receipt)
        if r.get('promoted'):
            path = Path(r['effective_bundle'])
            if not path.is_file() or sha(path) != r['effective_bundle_sha256']:
                raise ValueError('Accepted supplemental bundle changed')
            return path
    return Path(job) / 'artifacts/analysis_bundle_verified.json'


def completed_topic_selection(request,choices,command,workspace,timeout,model_call):
    contract=digest({name:sha(Path(__file__).with_name(name)) for name in (
        'cwh_author_batches.py','cwh_claim_synthesis.py','cwh_ranked_selection.py','cwh_editorial_selection.py')})
    cache_key=digest({'request':request,'choices':choices,'command':command,'contract':contract})
    path=workspace/(cache_key+'.completed.json')
    if path.exists():
        record=read(path);payload=record['payload']
        if record['payload_sha256']!=digest(payload) or proofs(payload['run'])!=record['native_proofs']:
            raise ValueError('Completed topic selection changed')
        return copy.deepcopy(payload['decision']),{**copy.deepcopy(payload['run']),'cache_reused':True,'seconds':0}
    decision,run=native_topic_synthesis(request,choices,command,workspace,timeout,model_call,reuse_cache=True)
    native_proofs=proofs(run)
    if native_proofs:
        payload={'decision':decision,'run':run}
        atomic_write_json(path,{'payload':payload,'payload_sha256':digest(payload),'native_proofs':native_proofs})
    return decision,run


def supplement(controller, runner, stage):
    import run_cwh_compiled_worker as worker
    from cwh_adaptive_web_research import agenda_order
    from run_cwh_batched_viewpoints import merge_topic_bundles
    from cwh_scoped_process import run_scoped_command
    from cwh_screen_bridge import materialize_screen
    from cwh_search_budget import query_budget_evidence
    from run_cwh_resumable_pipeline import validate_analysis_bundle, complete_compiled_bundle

    policy = controller.contract['automatic_remaining_research']
    job = runner.root
    ws = job / 'worker/domestic_remaining_research'
    ws.mkdir(parents=True, exist_ok=True)
    receipt_path = job / 'artifacts/remaining_research_receipt.json'
    base_path = job / 'artifacts/analysis_bundle_verified.json'
    baseline = read(base_path)
    receipt = {'status': 'running', 'promoted': False, 'baseline_sha256': sha(base_path),
               'operations': [], 'raw_completion': {}, 'warnings': [],
               'clock_origin_epoch': runner.state['budget_started_epoch']}
    extraction_end, synthesis_end, review_end = deadlines(runner.state['budget_started_epoch'], controller.contract, policy)
    receipt['deadlines_epoch'] = {'extraction': extraction_end, 'synthesis': synthesis_end, 'review': review_end}

    def checkpoint():
        receipt['elapsed_seconds'] = round(time.time() - runner.state['budget_started_epoch'], 3)
        atomic_write_json(receipt_path, receipt)

    primary = job / 'worker/domestic_viewpoints'
    if not (primary / 'prepared_research.json').exists() or review_end - time.time() < policy['minimum_start_seconds']:
        receipt['status'] = 'skipped_insufficient_time_or_no_primary_collection'
        checkpoint()
        return receipt
    prepared_record = read(primary / 'prepared_research.json')
    if prepared_record['payload_sha256'] != digest(prepared_record['payload']):
        raise ValueError('Primary acquired sources changed')
    prepared = copy.deepcopy(prepared_record['payload'])
    packets, plans, observed = (prepared[k] for k in ('packets', 'topic_plans', 'observed'))
    primary_task = read(job / 'tasks/domestic_viewpoints.json')
    plan = read(primary_task['inputs']['research_plan'])
    index = read(primary_task['inputs']['public_corpus_index'])
    corpus_path = Path(primary_task['inputs']['public_corpus_index']).with_name('public_article_evidence.json')
    if sha(corpus_path) != index['source_sha256']:
        raise ValueError('Supplement input corpus changed')
    author = read(primary / 'author_decisions.json')
    decisions = {d['topic']: copy.deepcopy(d) for d in author['decisions']}
    sem = json.loads(os.environ['CWH_SEMANTIC_COMMAND_JSON'])
    search = json.loads(os.environ['CWH_SEARCH_COMMAND_JSON'])
    cache_root = primary / 'article_readings'
    baseline_pools = {t['topic']: t for t in baseline['research_audit']['domestic_media_research']['candidate_pool_by_topic']}
    deferred = {t: copy.deepcopy(p.get('reading_scope', {}).get('semantic_reading_deferrals', [])) for t, p in baseline_pools.items()}
    modified, eligible_added, new_runs = set(), set(), []
    completed_rounds = {}
    choices = {t: {r['id']: r for r in d['items']} for t, d in decisions.items()}
    for packet in packets:
        packet['_reading_cache_root'] = str(cache_root)
    state_key=digest({'baseline':receipt['baseline_sha256'],'primary':prepared_record['payload_sha256'],
        'policy':policy,'command':sem,'search':search,'reading_prompt':reading_prompt(bounded=True)})
    state_path=ws/'source_checkpoint.json'
    if state_path.exists():
        cached=read(state_path);payload=cached['payload']
        if cached.get('key')!=state_key or cached.get('payload_sha256')!=digest(payload):
            raise ValueError('Supplement source checkpoint changed')
        if proofs(payload['new_runs'])!=cached['native_proofs']:
            raise ValueError('Supplement native provenance changed')
        prepared=payload['prepared'];packets,plans,observed=(prepared[k] for k in ('packets','topic_plans','observed'))
        choices=payload['choices'];deferred=payload['deferred'];new_runs=payload['new_runs']
        modified=set(payload['modified']);eligible_added=set(payload['eligible_added'])
        completed_rounds=payload['completed_rounds'];receipt=payload['receipt']
        receipt['resumed_completed_collection']=True

    def save_sources():
        payload={'prepared':prepared,'choices':choices,'deferred':deferred,'new_runs':new_runs,
            'modified':sorted(modified),'eligible_added':sorted(eligible_added),
            'completed_rounds':completed_rounds,'receipt':receipt}
        atomic_write_json(state_path, {'key':state_key,'payload':payload,'payload_sha256':digest(payload),
            'native_proofs':proofs(new_runs)})
        atomic_write_json(ws / 'reading_choices.json', choices)
        checkpoint()

    def read_articles(packet, candidates):
        topic = packet['topic'];pending = []
        prompt = reading_prompt(bounded=True)
        _,mechanical=worker.author_transport_with_fixed_unread_web({**packet,'items':candidates})
        for item_id,choice in mechanical.items():
            choices[topic][item_id]=choice;modified.add(topic)
            deferred[topic]=[r for r in deferred[topic] if r['id']!=item_id]
            if not any(o.get('kind')=='mechanical_article_disposition' and o.get('topic')==topic
                       and o.get('id')==item_id for o in receipt['operations']):
                receipt['operations'].append({'kind':'mechanical_article_disposition','topic':topic,
                    'id':item_id,'reason':choice['reason']})
        for item in candidates:
            if item['id'] in mechanical:continue
            cached = load_reading(cache_root, reading_key(packet, item, prompt, sem), item['id'])
            if cached:
                choice, run = cached
                choices[topic][item['id']] = choice;new_runs.append(run)
                deferred[topic] = [r for r in deferred[topic] if r['id'] != item['id']]
                modified.add(topic)
                if choice['decision'] == 'eligible':eligible_added.add(topic)
                receipt['operations'].append({'kind': 'article_cache_reuse', 'topic': topic, 'id': item['id']})
            else:pending.append(item)
        groups = partition_author_packet({'items': pending}, max_items=3) if pending else []
        for group_no, group in enumerate(groups):
            ids = [r['id'] for r in group['items']]
            if extraction_end - time.time() < policy['minimum_dispatch_seconds']:
                left = [r['id'] for g in groups[group_no:] for r in g['items']]
                failure = interruption(TimeoutError('Protected synthesis/review deadline reached before dispatch'))
                rows, missing = defer_reading(left, failure)
                deferred[topic] = [r for r in deferred[topic] if r['id'] not in left] + rows
                choices[topic].update({r['id']: r for r in missing});modified.add(topic)
                receipt['operations'].append({'kind': 'reading_not_dispatched', 'topic': topic, 'ids': ids})
                break
            operation_key = digest({'topic': topic, 'items': group['items']})
            local_ws = operation_workspace(ws/'readings',operation_key)
            local = {**packet, 'items': group['items'], 'screened_readings': [], 'screen_integration_active': False}
            try:
                result, run = worker.author_topic_decisions([local], prompt, sem, local_ws,
                    time.monotonic() + min(policy['maximum_reading_seconds'], extraction_end-time.time()),
                    reuse_cache=True, reading_only=True, allow_article_batches=False,
                    maximum_request_seconds=policy['maximum_reading_seconds'], future_topic_reserve_seconds=0)
            except (HostModelError, SemanticResponseError, TimeoutError) as exc:
                failure = interruption(exc)  # Auth/quota errors propagate; no provider fallback.
                rows, missing = defer_reading(ids, failure)
                deferred[topic] = [r for r in deferred[topic] if r['id'] not in ids] + rows
                choices[topic].update({r['id']: r for r in missing})
                receipt['operations'].append({'kind': 'reading_incomplete', 'topic': topic, 'ids': ids, 'failure': failure})
                modified.add(topic);save_sources();continue
            for choice in result[0]['items']:
                item = next(r for r in group['items'] if r['id'] == choice['id'])
                save_reading(cache_root, reading_key(packet, item, prompt, sem), choice, run)
                choices[topic][choice['id']] = choice
                deferred[topic] = [r for r in deferred[topic] if r['id'] != choice['id']]
                if choice['decision'] == 'eligible':eligible_added.add(topic)
            new_runs.append(run);modified.add(topic)
            receipt['operations'].append({'kind': 'articles_read', 'topic': topic, 'ids': ids, 'run': run})
            save_sources()

    # Complete only the unread subset of the original50, using the existing
    # multi-topic full-article contract once; never resubmit the original50.
    screen = primary / 'sample_screen'
    if (screen / 'job/model/sources.json').exists():
        originals = {f'r{n}': row for n, row in enumerate(read(corpus_path)['candidates'], 2)}
        selected = read(screen / 'job/model/sources.json')
        done = {r['id'] for r in read(screen / 'job/model/article_decisions.json')}
        todo = [r for r in selected if r['id'] not in done]
        receipt['raw_completion'] = {'queued': len(selected), 'initial_completed': len(done),
                                     'submitted_ids': [r['id'] for r in todo], 'additional_completed_ids': []}
        if todo and extraction_end-time.time() >= policy['minimum_dispatch_seconds'] + 30:
            raw_ws = ws / 'raw_completion';raw_ws.mkdir(exist_ok=True)
            atomic_write_json(raw_ws / 'records.json', todo)
            shutil.copy2(screen / 'agenda.json', raw_ws / 'agenda.json')
            allowance = min(policy['raw_completion_budget_seconds'], int(extraction_end-time.time()-10))
            command = [sys.executable, str(Path(__file__).parent/'fast_screen/native_screen_samples.py'),
                '--model', os.environ['CWH_SCREEN_MODEL'], '--records', str(raw_ws/'records.json'),
                '--agenda', str(raw_ws/'agenda.json'), '--out', str(raw_ws/'job'), '--budget-seconds', str(allowance), '--run']
            raw_receipt=raw_ws/'completed_collection.json'
            if raw_receipt.exists():
                prior_raw=read(raw_receipt)
                if prior_raw['input_sha256']!=digest(todo) or any(not Path(path).is_file() or sha(path)!=value
                        for path,value in prior_raw['artifacts'].items()):
                    raise ValueError('Completed raw supplement changed')
                code=0
            else:
                if (raw_ws/'job').exists():
                    # A native collection can finish before local conversion
                    # fails. Verify it, then resume conversion without a call.
                    launch=read((raw_ws/'job').with_suffix('.native_launch.json'))
                    sources=read(raw_ws/'job/model/sources.json')
                    source_map={r['id']:r['content'] for r in todo}
                    if (not launch.get('run_requested') or launch.get('requested_model')!=os.environ['CWH_SCREEN_MODEL']
                            or {r['id'] for r in sources}!=set(source_map)
                            or any(r['content']!=source_map[r['id']] for r in sources)
                            or not (raw_ws/'job/results_guarded/candidates_pending_independent_review.json').is_file()):
                        raise ValueError('Incomplete raw supplement needs diagnosis; refuse blind repeat')
                    code=0;receipt['raw_completion']['completed_native_collection_reused']=True
                else:
                    with (raw_ws/'screen.log').open('w', encoding='utf-8') as log:
                        code = run_scoped_command(command, cwd=raw_ws, env=os.environ.copy(), stdout=log,
                                                  timeout=min(allowance+8, extraction_end-time.time()))
            if code:
                raise HostModelError('Supplemental raw screen failed; retain exact unread queue', code)
            if not raw_receipt.exists():
                atomic_write_json(raw_receipt,{'input_sha256':digest(todo),
                    'artifacts':{str(path):sha(path) for path in (raw_ws/'job').rglob('*') if path.is_file()}})
            bytopic, quarantine, runs = materialize_screen(raw_ws/'job', originals, [t['topic'] for t in plan['topics']])
            completed = read(raw_ws/'job/model/article_decisions.json')
            receipt['raw_completion']['additional_completed_ids'] = [r['id'] for r in completed]
            receipt['raw_completion']['quarantine'] = quarantine
            new_runs.extend(runs)
            for packet in packets:
                topic = packet['topic'];known = {r.get('record_id') for r in packet['items']}
                for row in bytopic[topic]:
                    if row['record']['record_id'] in known:continue
                    item = make_packet(topic,packet['period'],[row['record']],{'queries':[]},[])['items'][0]
                    item['id'] = 'r'+str(1+max([int(r['id'][1:]) for r in packet['items'] if r['origin']=='raw_monitoring']+[0]))
                    packet['items'].append(item);known.add(item['record_id'])
                    choices[topic][item['id']] = {'id': item['id'], **copy.deepcopy(row['decision'])}
                    modified.add(topic)
                    if row['decision']['decision']=='eligible':eligible_added.add(topic)
            save_sources()

    # Retry incomplete reads only. A completed cached exclusion is a completed
    # reading, not a reason to rerun it when a batch layout changes.
    for packet in packets:
        ids = {r['id'] for r in deferred[packet['topic']]}
        ids.update(r['id'] for r in packet['items'] if r.get('content') and r['id'] not in choices[packet['topic']])
        read_articles(packet, [r for r in packet['items'] if r['id'] in ids and r.get('content')])

    voice_counts = {t['topic']: len({(e.get('speaker_name'), e.get('speaker_role'))
        for c in t.get('clusters',[]) for e in c.get('evidence',[])}) for t in baseline['viewpoints']['by_topic']}
    weak = sorted([i for i,p in enumerate(packets) if voice_counts[p['topic']] < policy['target_verified_voices_per_topic']],
                  key=lambda i:voice_counts[packets[i]['topic']])
    # Multi-topic raw reading is reused for every agenda item. A short first
    # queue does not exhaust the corpus; revisit only explicit unread reserves.
    reserve_file=screen/'job/filter/remaining_records.json'
    priority_file=screen/'job/filter/priority_audit.csv'
    if reserve_file.exists() and priority_file.exists():
        reserve_records=read(reserve_file)
        with priority_file.open(encoding='utf-8-sig',newline='') as handle:
            priority_rows=list(csv.DictReader(handle))
        agenda=read(screen/'agenda.json')
        all_records={r['id']:r for r in read(screen/'records.json')}
        done_ids={r['id'] for r in read(screen/'job/model/article_decisions.json')}
        done_ids.update(receipt.get('raw_completion',{}).get('additional_completed_ids',[]))
        for op in receipt['operations']:
            if op['kind']=='raw_reserve_recall':done_ids.update(op['completed_ids'])
        for position in weak:
            packet=packets[position];topic=packet['topic']
            previous_ops=[o for o in receipt['operations'] if o['kind']=='raw_reserve_recall' and o['topic']==topic]
            for recall_no in range(len(previous_ops)+1,policy.get('raw_recall_rounds_per_topic',1)+1):
                # Protect an actual feedback-led search after this batch.
                recall_end=min(extraction_end-policy.get('protected_feedback_search_seconds',110),
                               time.time()+policy.get('raw_recall_budget_seconds',150))
                if recall_end-time.time()<60:break
                # An existing unselected nomination backlog needs selection,
                # not another reading of the same source or unrelated corpus.
                nominated={(c.get('speaker'),c.get('role')) for d in choices[topic].values()
                    if d.get('decision')=='eligible' for c in d.get('claims',[]) if c.get('speaker')}
                if len(nominated)>=policy['target_verified_voices_per_topic']:
                    eligible_added.add(topic);modified.add(topic)
                    receipt['operations'].append({'kind':'existing_nominee_backlog_selection','topic':topic,
                        'nominated_subjects':len(nominated)});break
                aliases=agenda['topic_aliases'][agenda['topics'].index(topic)]
                selected,selection_audit=rank_reserves(reserve_records,priority_rows,topic,aliases,
                    [all_records[i] for i in done_ids],limit=policy.get('raw_recall_articles_per_round',6),
                    max_chars=policy.get('raw_recall_body_characters',60000))
                if not selected:break
                # Short path keeps native host receipts below Win32 MAX_PATH.
                rws=job/'rc'/f'{position+1}-{recall_no}'
                try:
                    bytopic,quarantine,runs,result=collect_subset(rws,selected,originals,screen/'agenda.json',
                        os.environ['CWH_SCREEN_MODEL'],recall_end,policy.get('raw_recall_budget_seconds',150))
                except (HostModelError,SemanticResponseError,TimeoutError) as exc:
                    failure=interruption(exc)
                    receipt['operations'].append({'kind':'raw_reserve_recall_incomplete','topic':topic,
                        'submitted_ids':[r['id'] for r in selected],'failure':failure})
                    save_sources();break
                done_ids.update(result['completed_ids']);new_runs.extend(runs)
                for target in packets:
                    target_topic=target['topic'];known={r.get('record_id') for r in target['items']}
                    for row in bytopic[target_topic]:
                        if row['record']['record_id'] in known:continue
                        item=make_packet(target_topic,target['period'],[row['record']],{'queries':[]},[])['items'][0]
                        item['id']='r'+str(1+max([int(r['id'][1:]) for r in target['items'] if r['origin']=='raw_monitoring']+[0]))
                        target['items'].append(item);known.add(item['record_id'])
                        choices[target_topic][item['id']]={'id':item['id'],**copy.deepcopy(row['decision'])}
                        modified.add(target_topic)
                        if row['decision']['decision']=='eligible':eligible_added.add(target_topic)
                receipt['operations'].append({'kind':'raw_reserve_recall','topic':topic,'round':recall_no,
                    **result,'selection_audit':selection_audit,'quarantine':quarantine,'runs':runs})
                save_sources()
    for position in weak:
        packet, observation = packets[position], observed[position]
        topic = packet['topic']
        # Previously discovered but unfetched pages are still useful work.
        # Their existing query IDs stay intact; metadata ranking is not approval.
        def read_previous_discoveries():
            previously_fetched=any(o.get('kind')=='previous_discoveries_fetched' and o.get('topic')==topic for o in receipt['operations'])
            if extraction_end-time.time() >= policy['minimum_dispatch_seconds']+40 and not previously_fetched:
                unfetched=[r for r in packet['items'] if r['origin']=='web' and not r.get('content')
                    and r.get('full_text_status')=='not_fetched_bounded_budget']
                if unfetched:
                    from cwh_reading_priority import prioritize_pages
                    pws=ws/f'previous-discoveries-{position+1}';pws.mkdir(exist_ok=True)
                    wanted={r['url'] for r in unfetched}
                    narrowed=copy.deepcopy(observation)
                    for q in narrowed['queries']:q['results']=[r for r in q['results'] if r['url'] in wanted]
                    urls=prioritize_pages(narrowed,topic,policy['pages_per_round'],
                        [r['url'] for r in unfetched[:policy['pages_per_round']]],sem,pws,25,worker.semantic_json,
                        context={'period':packet['period'],'verified_voices':voice_counts[topic],
                                 'task':'Seek independent analysis, affected groups, concrete mechanisms; primary meeting facts already read.'})
                    pages=worker.cached_public_pages(pws,urls,timeout=8)
                    byurl={r['url']:r for r in packet['items']}
                    fetched=[]
                    for page in pages:
                        item=byurl[page['url']]
                        item.update(content=page.get('source_text',''),capture=page,
                            title=page.get('page_title') or item['title'],full_text_status=page.get('status','access_failed'))
                        item['segment_scope']='p'+hashlib.sha256((item['url']+'\n'+item['content']).encode()).hexdigest()[:12]
                        if item['content']:fetched.append(item)
                    modified.add(topic)
                    receipt['operations'].append({'kind':'previous_discoveries_fetched','topic':topic,
                        'acquired_urls':[r['url'] for r in fetched]})
                    read_articles(packet,fetched);save_sources()
        for round_no in range(completed_rounds.get(topic,0)+1,policy['max_rounds_per_weak_topic']+1):
            if extraction_end-time.time() < policy['minimum_dispatch_seconds']+50:break
            previous = [q['query'] for q in observation['queries']]
            qws = ws / f'search-{position+1}-{round_no}';qws.mkdir(exist_ok=True)
            request = {'topic':topic, 'period':packet['period'], 'meeting_context':packet.get('meeting_context'),
                       'previous_queries':previous, 'verified_voices':voice_counts[topic],
                       'reading_rejection_feedback':rejection_feedback(packet,choices[topic],
                           deferred_ids=[r['id'] for r in deferred[topic]]),
                       'count':policy['additional_queries_per_round']}
            try:
                result, run = worker.semantic_json(request,
                    '为当前缺少独立解读的议题设计count条新的公开搜索词，不调用工具。只返回JSON {"items":[{"query":"..."}]}。'
                    'items必须恰好count项，每项只有query一个字段，不使用query_2等编号键。'
                    '不得重复previous_queries。根据当前会议原文具体措施，找专家、律师、受影响群体的机制分析、难点、建议。'
                    '必须利用reading_rejection_feedback中已有逐篇剔除理由调整方向：旧条例、其他会议、纯通稿、营销或缺少原文分别处理；'
                    'pending_not_negative只是未读，不能宣称没有观点。若旧法旧会议为主，改用当前会议措施、数字组合、当前月份与通俗措辞，'
                    '寻找本期媒体自身或专业实务分析，不只给旧查询追加“专家解读”，避免堆砌很长的OR条件。'
                    '不要反复只搜会议通稿，不把同场其他政策挪来，不编造措施、人名或年份。每条必须含当前年份。',
                    sem,qws,'query-planning',min(35,extraction_end-time.time()-60),reuse_cache=True)
            except (HostModelError,SemanticResponseError,TimeoutError) as exc:
                failure=interruption(exc);receipt['warnings'].append('Additional query planning incomplete: '+str(failure));break
            queries=query_values(result)
            if (not isinstance(queries,list) or len(queries)!=policy['additional_queries_per_round'] or
                    len(set(queries))!=len(queries) or any(not isinstance(q,str) or not q.strip() or
                    not query_is_new(q,previous) or packet['period']['start'][:4] not in q for q in queries)):
                receipt['warnings'].append('Targeted query planner returned invalid/repeated queries: '+topic);break
            extra=collect_topic({'topic':topic,'supplemental_search_tasks':[
                {'source_id':'remaining_targeted','route':'open_web','query':q} for q in queries]},
                packet['period'],search,qws,min(65,extraction_end-time.time()-60))
            offset=len(observation['queries'])
            for n,q in enumerate(extra['queries'],offset+1):q['query_id']='q'+str(n)
            observation['queries'].extend(extra['queries'])
            observation.setdefault('supplemental_host_runs',[]).append(extra['host_run'])
            existing={r['url'] for r in packet['items'] if r['origin']=='web'}
            urls=[]
            for q in extra['queries']:
                for r in q['results']:
                    if r['url'] not in existing and r['url'] not in urls:urls.append(r['url'])
            attempted=sum(r['origin']=='web' and r.get('full_text_status')!='not_fetched_bounded_budget' for r in packet['items'])
            room=max(0,36-attempted)
            pages=worker.cached_public_pages(qws,urls[:min(policy['pages_per_round'],room)],timeout=min(8,max(.1,extraction_end-time.time())))
            fresh=make_packet(topic,packet['period'],[],extra,pages)
            max_id=max([int(r['id'][1:]) for r in packet['items'] if r['origin']=='web']+[0])
            rows=[r for r in fresh['items'] if r['url'] not in existing]
            for n,r in enumerate(rows,max_id+1):r['id']='w'+str(n)
            packet['items'].extend(rows);modified.add(topic)
            _,fixed=worker.author_transport_with_fixed_unread_web({**packet,'items':rows})
            choices[topic].update(fixed)
            receipt['operations'].append({'kind':'targeted_search','topic':topic,'round':round_no,
                'queries':extra['queries'],'new_acquired_urls':[r['url'] for r in rows if r.get('content')],
                'reading_rejection_feedback':request['reading_rejection_feedback'],'planning_run':run})
            completed_rounds[topic]=round_no
            save_sources()
            read_articles(packet,[r for r in rows if r.get('content')])
            save_sources()
            if not rows:break
        read_previous_discoveries()
    save_sources()
    if not modified:
        receipt['status']='queues_unchanged';checkpoint();return receipt

    # Recompile unchanged topics without any native calls. Only new eligible
    # claims trigger topic selection; grouping failures keep the original topic.
    parts=[]
    registry=read(primary_task['inputs']['source_registry'])
    for position,packet in enumerate(packets):
        topic=packet['topic'];decision=copy.deepcopy(decisions[topic])
        if topic in eligible_added:
            if synthesis_end-time.time()<policy['minimum_dispatch_seconds']:
                receipt['warnings'].append('New candidates remain ungrouped: '+topic)
                packet=copy.deepcopy(prepared_record['payload']['packets'][position])
                observation=prepared_record['payload']['observed'][position]
                local_deferrals=baseline_pools[topic]['reading_scope'].get('semantic_reading_deferrals',[])
            else:
                proposed=[choices[topic][r['id']] for r in packet['items']]
                request=synthesis_packet(packet,proposed)
                request['formal_selection']={**request.get('formal_selection',{}),'selection_mode':'ranked_positive_v1'}
                request['previously_verified_claims']=[e for t,e in body_claims(baseline) if t==topic]
                tws=ws/f'synthesis-{position+1}';tws.mkdir(exist_ok=True)
                try:
                    decision,run=completed_topic_selection(request,proposed,sem,tws,
                        min(100,synthesis_end-time.time()),worker.semantic_json)
                    new_runs.append(run);decision['topic']=topic
                    observation=observed[position];local_deferrals=deferred[topic]
                except (HostModelError,SemanticResponseError,TimeoutError,ValueError) as exc:
                    if isinstance(exc,HostModelError):interruption(exc)
                    receipt['warnings'].append('New candidates preserved without grouping: '+topic+': '+str(exc))
                    packet=copy.deepcopy(prepared_record['payload']['packets'][position])
                    observation=prepared_record['payload']['observed'][position]
                    decision=copy.deepcopy(decisions[topic])
                    local_deferrals=baseline_pools[topic]['reading_scope'].get('semantic_reading_deferrals',[])
        else:
            decision['items']=[choices[topic][r['id']] for r in packet['items']]
            observation=observed[position];local_deferrals=deferred[topic]
        part=compile_topic(packet,decision,observation,plans[position],controller.contract['execution_profile'],
            registry['version'],author['run']['session_id'],reading_deferrals=local_deferrals)
        pool=part['research_audit']['domestic_media_research']['candidate_pool_by_topic'][0]
        pool['saturation']['allocated_query_limit']=len(observation['queries'])
        pool['saturation']['budget_stop']=query_budget_evidence(pool['saturation'],controller.contract['execution_profile'])
        pool['supplemental_search_runs']=observation.get('supplemental_host_runs',[])
        parts.append(part)
    merged=merge_topic_bundles(agenda_order(parts,[r['topic'] for r in index['topics']]),
        [r['topic'] for r in index['topics']],index['candidate_count'],str(uuid.uuid4()))
    merged['metadata'].update(execution_profile=controller.contract['execution_profile'],
        monitoring_start=plan['monitoring_period']['start'],monitoring_end=plan['monitoring_period']['end'],
        report_agenda=controller.contract['agenda'],transport='automatic_remaining_research',
        authoring_batch_run_ids=list(dict.fromkeys([*baseline['metadata'].get('authoring_batch_run_ids',[]),
            *[r['session_id'] for r in new_runs if r.get('session_id')]])))
    child=job/'rr';artifacts=child/'artifacts';artifacts.mkdir(parents=True,exist_ok=True)
    shutil.copy2(corpus_path,artifacts/'public_article_evidence.json')
    shutil.copy2(primary_task['inputs']['public_corpus_index'],artifacts/'public_corpus_index.json')
    merged=complete_compiled_bundle(merged,read(corpus_path),[r['topic'] for r in index['topics']],controller.contract['execution_profile'])
    draft=artifacts/'analysis_bundle.json';atomic_write_json(draft,merged)
    problems=validate_analysis_bundle(draft,[r['topic'] for r in index['topics']],require_semantic_review=False,allow_deferred_corpus=True,allow_claim_repair=True)
    if problems:
        receipt.update(status='new_candidates_draft_invalid',warnings=receipt['warnings']+problems);checkpoint();return receipt
    if review_end-time.time()<60:
        receipt['status']='new_candidates_waiting_independent_review';checkpoint();return receipt
    # Use the exact production independent-review evaluator and gates. The
    # nested workspace owns new outputs; accepted primary artifacts stay intact.
    from run_cwh_resumable_pipeline import CwhPipeline, build_specs
    shutil.copy2(job/'artifacts/CWH舆情情况_标准总表.xlsx',artifacts/'CWH舆情情况_标准总表.xlsx')
    class ReviewRunner:
        root=child
        input_contract=controller.contract
        def remaining_budget_seconds(self,stage_id=''):
            return max(0,min(review_end-time.time(),runner.remaining_budget_seconds(stage.stage_id)))
        def run_command(self,stage_id,command,**kwargs):
            kwargs['timeout_seconds']=min(kwargs.get('timeout_seconds') or 1e9,self.remaining_budget_seconds())
            return runner.run_command(stage.stage_id,command,**kwargs)
        def __getattr__(self,name):return getattr(runner,name)
    child_controller=CwhPipeline.__new__(CwhPipeline)
    child_controller.job_dir=child;child_controller.artifacts=artifacts;child_controller.tasks=child/'tasks'
    child_controller.tasks.mkdir(exist_ok=True);child_controller.report=child/'report';child_controller.contract=controller.contract
    verification_spec=next(s for s in build_specs() if s.stage_id=='domestic_evidence_verification')
    outcome=child_controller.domestic_evidence_verification(ReviewRunner(),verification_spec)
    receipt['independent_review_status']=outcome.status
    if outcome.status!='succeeded':
        receipt.update(status='new_candidates_waiting_independent_review',warnings=receipt['warnings']+[outcome.message]);checkpoint();return receipt
    verified=artifacts/'analysis_bundle_verified.json'
    fresh=read(verified)
    # Additional research must not silently reduce the already verified body.
    if len(body_claims(fresh)) < len(body_claims(baseline)):
        receipt['status']='reviewed_supplement_kept_in_reserve_body_would_shrink';checkpoint();return receipt
    target=job/'artifacts/analysis_bundle_remaining_verified.json';shutil.copy2(verified,target)
    receipt.update(status='completed',promoted=True,effective_bundle=str(target),effective_bundle_sha256=sha(target),
        primary_body_claims=len(body_claims(baseline)),effective_body_claims=len(body_claims(fresh)),
        independent_review_artifacts=str(artifacts))
    checkpoint();return receipt
