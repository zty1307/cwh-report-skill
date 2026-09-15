"""Review-derived display headings; frozen claims and original titles never change."""
import copy
import hashlib
import json
import re
from cwh_writing_rules import writing_rules, judgment_heading


HEADING_REVIEW_PROMPT = '''同时返回heading_reviews数组，每个headings输入ID恰好一次：
{"id":"h1","verdict":"supported|needs_revision|uncertain","rationale":"具体说明标题对应哪些论据、是否夸大或改变立场","supporting_claim_ids":["e1"],"scope_preserved":true或false,"replacement":null或{"text":"有出处的单一中心判断","verdict":"supported","rationale":"具体支持理由"}}。
标题只能依据本标题claim_ids内的原文；观点有revision时以收窄后的观点为准。不能把政策发布事实写成专家肯定，不能把建议写成已经实现的效果，保留可能、前提、风险等限定。一级标题提炼主判断，分簇标题区分具体机制、条件、影响或建议；避免不同簇反复说同一件事。不要为了凑正面、凑簇数或换动词新增立场。标题supported时replacement为null；needs_revision可提出已逐项核对原文的替代标题；实在没有依据则uncertain且replacement为null。不要改写证据原文或发言人身份。'''
HEADING_REVIEW_PROMPT += '\n替代一级标题12—26个汉字，分簇标题10—24个汉字；只保留一个中心判断，不带专家强调、媒体认为等套头，不堆砌并列论点。只有客观细则而没有评价依据时用中性标题，不凭空补肯定或认可。'
HEADING_REVIEW_PROMPT += '\n专家对机制或影响的实质判断可准确概括为认为、强调，不要求原文逐字出现同一个标题动词；但政策发布事实不能改成舆论赞扬、已经实现的效果或额外主张。'
HEADING_REVIEW_PROMPT += '\n标题语义受支持但带“机构解读”“专家强调”“媒体认为”“审慎提示”等来源标签或审核动作套头，也应needs_revision：直接写具体判断，不把审核过程当观点。不要改变真实批评、风险或建议的强度，不因有部分审慎建议就将同簇明确批评一律软化为提示。'
HEADING_REVIEW_PROMPT += '\n单独的“认为/建议/认可/期待”等是合法判断动词，不是来源标签；不能仅因标题以“认为”开头就判needs_revision或删去它。“专家认为/机构解读”等额外来源套头才须去掉；保留原判断立场，标题是否改写取决于语义、具体程度和单一中心，而不是要求所有标题无态度动词。'
HEADING_REVIEW_PROMPT += '\n' + writing_rules()['viewpoint']['heading_support_rule']
HEADING_REVIEW_PROMPT += '\ncluster_index不为null时，逐条核对该簇全部保留claim_ids都支持同一个中心判断；supporting_claim_ids必须完整覆盖，不得只选适合新标题的一名主体而把其他不同对象或机制留在标题下。无法形成共同判断就uncertain，不能把多个中心用顿号拼起来，也不能删除组员的观点。'
HEADING_REVIEW_PROMPT += '\ncluster_index为null是一级议题标题。scope_preserved须为原生布尔值，确认替代标题仍保留输入topic实际全部政策对象，不要求不同立场赞同同一评价。议题有多个政策对象时，不能为缩短标题只剩一个子对象或第一簇机制；无法提炼有依据的共同判断时直接用输入topic作中性标题并确认范围，不硬拼多个结论。'


def cross_topic_exact_duplicate_groups(analysis):
    """Flag identical declared actors/roles/URLs/claims; never choose a topic."""
    groups, ordinal = {}, 0
    for topic in analysis['viewpoints']['by_topic']:
        for cluster in topic['clusters']:
            for evidence in cluster['evidence']:
                ordinal += 1
                name, role = evidence.get('speaker_name'), evidence.get('speaker_role') or ''
                url = evidence.get('url') or evidence.get('source_url')
                claim = (evidence.get('formal_claim') or '').strip().rstrip('。')
                if not name or not url or not claim:
                    continue
                key = (name, role, url, claim)
                groups.setdefault(key, []).append({'claim_id': f'e{ordinal}',
                    'topic': topic['topic'], 'evidence_id': evidence.get('evidence_id')})
    return [{'claim_ids': [r['claim_id'] for r in rows],
             'topics': [r['topic'] for r in rows],
             'evidence_ids': [r['evidence_id'] for r in rows]}
            for rows in groups.values() if len({r['topic'] for r in rows}) > 1]


def repair_runs(packet):
    """Read host-retained run records defensively; malformed metadata is inert."""
    rows = packet.get('heading_repair_runs')
    rows = list(rows) if isinstance(rows, list) else []
    rows.append(packet.get('heading_repair_run'))
    rows.append(packet.get('heading_original_run'))
    return {r['session_id']: r for r in rows if isinstance(r, dict)
            and isinstance(r.get('session_id'), str) and r['session_id']}


def review_retained_headings(analysis, packet, command, workspace, timeout):
    """Optional compact recheck after claim retention; never reuse old claim IDs."""
    from cwh_host_research import semantic_json, HostModelError
    manifest = heading_manifest(analysis)
    if not manifest or timeout < 25:
        return packet
    claims = [{"id": f'e{i}', **{k: ev.get(k, '') for k in
              ('formal_claim', 'source_excerpt', 'speaker_name', 'speaker_role')}}
              for i, ev in enumerate((ev for topic in analysis['viewpoints']['by_topic']
                  for cluster in topic['clusters'] for ev in cluster['evidence']), 1)]
    try:
        result, run = semantic_json({'headings': manifest, 'claims': claims},
            '只复审当前已独立核验观点对应的标题，返回heading_reviews，不修改观点或复做观点审核。'
            '这些是当前保留和收窄后的观点；原始旧短ID已经作废，按本输入ID审核。\n' + HEADING_REVIEW_PROMPT,
            command, workspace, 'retained-heading-review', min(90, timeout), reuse_cache=False)
        reviews = result.get('heading_reviews')
        ids = [r.get('id') for r in reviews if isinstance(r, dict)] if isinstance(reviews, list) else []
        if (not isinstance(reviews, list) or len(reviews) != len(manifest)
                or not all(isinstance(identity, str) for identity in ids)
                or len(ids) != len(manifest) or len(ids) != len(set(ids)) or set(ids) != {r['id'] for r in manifest}):
            return packet
        final = copy.deepcopy(packet)
        final['heading_reviews'] = [{**r, 'reviewer_run_id': run['session_id']} for r in reviews]
        final['heading_repair_runs'] = [run]
        final['heading_repair_run'] = run
        return final
    except (HostModelError, ValueError, TimeoutError):
        return packet


def repair_overlong_headings(packet, result, command, workspace, timeout):
    """One optional compact call for length/clear style faults, never truncation."""
    from cwh_host_research import semantic_json, HostModelError
    rows = result.get('heading_reviews')
    if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get('id'), str) for r in rows):
        return result
    manifest = {r['id']: r for r in packet['headings']}
    wanted = []
    for review in rows:
        if review['id'] not in manifest:
            continue
        row = manifest[review['id']]
        replacement = review.get('replacement')
        text = replacement.get('text') if isinstance(replacement, dict) else row['text']
        hi = writing_rules()['viewpoint']['topic_heading_cjk_range' if row['cluster_index'] is None else 'cluster_heading_cjk_range'][1]
        if not isinstance(text, str):
            continue
        faults = []
        if sum('\u4e00' <= c <= '\u9fff' for c in text) > hi:
            faults.append('标题过长')
        if re.search(r'(?:转向|转为)[^，。]{0,8}转变', text):
            faults.append('转向转变表达重复')
        if '被解读为' in text or re.search(r'(?:认为|认可|支持|建议|期待).*(?:的|配置)判断$', text):
            faults.append('介绍解读过程或判断标签代替具体判断；须核对原论断，不机械删词')
        verbs = '|'.join(re.escape(v) for v in writing_rules()['viewpoint']['attribution_verbs'])
        if re.match(r'^(?:认为|强调|建议|认可|肯定)?(?:机构解读|审慎提示|(?:专家|媒体|机构|舆论)(?:' + verbs + r'))', text):
            faults.append('来源标签或审核动作代替具体判断')
        if any(c in text for c in '，,；;'):
            faults.append('核查是否拼接多个中心判断；必要条件与一个判断不算双中心，不能只删除连接词掩盖拼接')
        if faults:
            wanted.append({**row, 'prior_review': review, 'target_max_cjk': hi, 'style_faults': faults})
    if not wanted or timeout < 15:
        return result
    identities = {r['id'] for r in wanted}
    claim_ids = {i for row in wanted for i in row['claim_ids']}
    claims = [copy.deepcopy(c) for c in packet['claims'] if c['id'] in claim_ids]
    by_id = {r['id']: r for r in result.get('reviews') or [] if isinstance(r, dict) and isinstance(r.get('id'), str)}
    for claim in claims:
        revision = (by_id.get(claim['id']) or {}).get('revision')
        if isinstance(revision, dict):
            claim['formal_claim'] = revision.get('formal_claim', claim['formal_claim'])
    try:
        repaired, run = semantic_json({'headings': wanted, 'claims': claims, 'sources': packet['sources']},
            '仅修正给定标题的长度或明确文风问题，其他标题不处理。按style_faults保留一个中心判断及必要条件；不要只去连接词而保留堆叠结论。返回{"heading_reviews":[...]}，每个输入ID一次。\n' + HEADING_REVIEW_PROMPT,
            command, workspace, 'heading-length-repair', min(45, timeout))
        patches = repaired.get('heading_reviews')
        if (not isinstance(patches, list) or len(patches) != len(identities)
                or not all(isinstance(r, dict) and isinstance(r.get('id'), str) for r in patches)
                or {r['id'] for r in patches} != identities):
            return result
        merged = copy.deepcopy(result)
        replacements = {r['id']: {**r, 'reviewer_run_id': run['session_id']} for r in patches}
        merged['heading_reviews'] = [replacements.get(r['id'], r) for r in rows]
        by_run = repair_runs(result)
        by_run[run['session_id']] = run
        merged['heading_repair_runs'] = list(by_run.values())
        merged['heading_repair_run'] = run
        return merged
    except (HostModelError, ValueError, TimeoutError):
        return result


def heading_manifest(analysis):
    rows, number = [], 0
    for ti, topic in enumerate(analysis['viewpoints']['by_topic']):
        groups = []
        for ci, cluster in enumerate(topic['clusters']):
            ids = []
            for _ in cluster['evidence']:
                number += 1
                ids.append(f'e{number}')
            if ids:
                groups.append((ci, cluster, ids))
        if not groups:
            continue
        rows.append({'id': f'h{len(rows)+1}', 'topic_index': ti, 'cluster_index': None,
                     'topic': topic['topic'], 'text': topic.get('heading', ''),
                     'claim_ids': [identity for _, _, ids in groups for identity in ids]})
        for ci, cluster, ids in groups:
            rows.append({'id': f'h{len(rows)+1}', 'topic_index': ti, 'cluster_index': ci,
                         'topic': topic['topic'], 'text': cluster.get('summary', ''), 'claim_ids': ids})
    return rows


def heading_input_digest(analysis):
    claims = [{k: ev.get(k) for k in ('evidence_id', 'formal_claim', 'source_excerpt', 'speaker_name', 'speaker_role')}
              for topic in analysis['viewpoints']['by_topic'] for cl in topic['clusters'] for ev in cl['evidence']]
    value = {'headings': heading_manifest(analysis), 'claims': claims}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def build_heading_audit(analysis, packet):
    manifest = heading_manifest(analysis)
    supplied = packet.get('heading_reviews')
    warnings, approved, fallbacks = [], [], []
    audit = {'version': '1.0', 'input_sha256': heading_input_digest(analysis),
             'reviewer_run_id': packet.get('reviewer_run_id'), 'reviews': copy.deepcopy(supplied or []),
             'heading_repair_run': packet.get('heading_repair_run'),
             'heading_original_run': packet.get('heading_original_run'),
             'heading_repair_runs': packet.get('heading_repair_runs') or [],
             'approved': approved, 'fallbacks': fallbacks, 'warnings': warnings}
    duplicates = cross_topic_exact_duplicate_groups(analysis)
    audit['cross_topic_exact_duplicates'] = duplicates
    if duplicates:
        warnings.append('存在同一声明主体、职务及原始URL的完全相同判断跨议题重用；须依据实际政策对象确认唯一归属，脚本不猜去向。')
    if not isinstance(supplied, list):
        warnings.append('本次独立审核未返回标题语义审核；不自动改写标题。')
        return audit
    identities = [r.get('id') for r in supplied if isinstance(r, dict)]
    expected = {r['id'] for r in manifest}
    if (len(identities) != len(supplied) or not all(isinstance(s, str) for s in identities)
            or len(identities) != len(set(identities)) or set(identities) != expected):
        warnings.append('标题审核ID覆盖不完整或重复；不采用任何替代标题。')
        return audit
    by_id = {r['id']: r for r in supplied}
    claims = [ev for topic in analysis['viewpoints']['by_topic'] for cl in topic['clusters'] for ev in cl['evidence']]
    verdicts = {r['evidence_id']: r.get('verdict') for r in packet.get('reviews') or []}
    supported = {f'e{i}': verdicts.get(ev['evidence_id']) == 'fully_supported' for i, ev in enumerate(claims, 1)}
    stances = tuple(writing_rules()['viewpoint']['heading_stance_verbs'])
    for row in manifest:
        review = by_id[row['id']]
        support_ids = review.get('supporting_claim_ids')
        valid_support = (isinstance(support_ids, list) and bool(support_ids)
                         and all(isinstance(s, str) for s in support_ids)
                         and len(support_ids) == len(set(support_ids))
                         and all(isinstance(s, str) and s in row['claim_ids'] and supported.get(s) for s in support_ids))
        if row['cluster_index'] is not None and valid_support and set(support_ids) != set(row['claim_ids']):
            valid_support = False
            warnings.append(f"{row['topic']}：分簇标题未覆盖全部保留成员，不采用仅部分主体支持的替代标题。")
        scope_valid = row['cluster_index'] is not None or review.get('scope_preserved') is True
        if not scope_valid:
            warnings.append(f"{row['topic']}：一级标题未确认完整政策对象范围，保留原议题名称。")
        verdict = review.get('verdict')
        replacement = review.get('replacement')
        text = row['text']
        certified = verdict == 'supported' and replacement is None
        if verdict == 'needs_revision' and isinstance(replacement, dict):
            text = replacement.get('text')
            certified = replacement.get('verdict') == 'supported' and bool(replacement.get('rationale'))
        if (not certified or not valid_support or not scope_valid or not review.get('rationale')
                or not packet.get('reviewer_run_id') or not isinstance(text, str)
                or not 4 <= len(text) <= 80
                or any(c in text for c in '\n\r')):
            warnings.append(f"{row['topic']} / {row['text']}：{review.get('rationale') or '未取得可采用的标题审核'}")
            if verdict in {'needs_revision', 'uncertain'} or not scope_valid or not valid_support:
                fallbacks.append({**row, 'display_text': row['topic'] if row['cluster_index'] is None else '相关报道'})
            continue
        if text.startswith(stances):
            text = judgment_heading(text)
        else:
            warnings.append(f"{row['topic']}：标题仅有客观信息支持，保留中性表述，不添加舆论肯定。")
        lo, hi = writing_rules()['viewpoint']['topic_heading_cjk_range' if row['cluster_index'] is None else 'cluster_heading_cjk_range']
        cjk = sum('\u4e00' <= c <= '\u9fff' for c in text)
        if not lo <= cjk <= hi:
            warnings.append(f"{row['topic']}：已核验标题长度{cjk}，超出写作建议{lo}—{hi}，不机械删去限定词。")
        known_runs = repair_runs(packet)
        approved.append({**row, 'display_text': text, 'supporting_claim_ids': support_ids,
                         'reviewer_run_id': review.get('reviewer_run_id') if review.get('reviewer_run_id') and review.get('reviewer_run_id') in known_runs else packet['reviewer_run_id']})
    return audit


def reviewed_display_headings(data):
    """Return only a current, complete host-recompiled audit; stale data is inert."""
    research = data.get('research_audit') or (data.get('analysis_bundle') or {}).get('research_audit') or {}
    audit = research.get('heading_quality') or {}
    if not audit.get('reviewer_run_id'):
        return {}
    original = {'viewpoints': copy.deepcopy(data.get('viewpoints') or {})}
    try:
        for row in (audit.get('approved') or []) + (audit.get('fallbacks') or []):
            topic = original['viewpoints']['by_topic'][row['topic_index']]
            target = topic if row['cluster_index'] is None else topic['clusters'][row['cluster_index']]
            field = 'heading' if row['cluster_index'] is None else 'summary'
            if target.get(field) not in (row['text'], row['display_text']):
                return {}
            target[field] = row['text']
        if audit.get('input_sha256') != heading_input_digest(original):
            return {}
    except (KeyError, IndexError, TypeError):
        return {}
    packet = {'heading_reviews': audit.get('reviews'), 'reviewer_run_id': audit['reviewer_run_id'],
              'heading_repair_run': audit.get('heading_repair_run'),
              'heading_original_run': audit.get('heading_original_run'),
              'heading_repair_runs': audit.get('heading_repair_runs') or [],
              'reviews': [{'evidence_id': ev['evidence_id'],
                           'verdict': (ev.get('semantic_review') or {}).get('verdict')}
                          for topic in data['viewpoints']['by_topic'] for cl in topic['clusters'] for ev in cl['evidence']]}
    rebuilt = build_heading_audit(original, packet)
    if rebuilt['approved'] != audit.get('approved') or rebuilt['fallbacks'] != audit.get('fallbacks'):
        return {}
    return {(r['topic_index'], r['cluster_index']): r['display_text'] for r in rebuilt['approved'] + rebuilt['fallbacks']}
