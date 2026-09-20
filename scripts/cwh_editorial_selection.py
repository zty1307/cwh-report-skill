"""Pre-freeze editorial selection; never rewrite or certify source meaning."""
import copy
import time

from cwh_writing_rules import writing_rules, formal_claim_char_count
from cwh_viewpoint_gate import independent_voice_keys


def author_layout_shortfalls(decision):
    """Count selected identities only; never decide whether judgments can merge."""
    groups = {g['key']: set() for g in decision.get('clusters') or []}
    populated = set()
    for item in decision.get('items') or []:
        if item.get('decision') != 'eligible':
            continue
        for claim in item.get('claims') or []:
            key = claim.get('cluster')
            if key not in groups or claim.get('formal_use') in {'reserve', 'excluded'}:
                continue
            populated.add(key)
            groups[key] |= independent_voice_keys([{'speaker_name': claim.get('speaker'),
                                                    'source': item.get('source')}])
    if len(populated) < 2:
        return []
    minimum = writing_rules()['viewpoint']['numbered_cluster_min_sources']
    return [{'key': key, 'sources': len(voices), 'required': minimum}
            for key, voices in groups.items() if key in populated and len(voices) < minimum]


def repair_author_layout_once(result, response, transport, restore, prompt, command,
                              workspace, deadline, model_call, run):
    """Optional native regrouping within the existing synthesis deadline.

    Failure retains the shape-valid selection, not just its first group. This
    does not certify the editorial contract or skip independent source review.
    """
    from cwh_host_research import HostModelError, SemanticResponseError
    from cwh_pipeline_runtime import atomic_write_json
    gaps = author_layout_shortfalls(result)
    if not gaps:
        return result, run
    subjects = independent_voice_keys([{'speaker_name': c.get('speaker'), 'source': row.get('source')}
        for row in result.get('items') or [] for c in row.get('claims') or []])
    remaining = deadline - time.monotonic()
    audit = {'kind': 'native_editorial_layout_repair', 'original_shortfalls': gaps,
             'original_response': copy.deepcopy(response), 'status': 'pending_no_budget'}
    repair_run = None
    if remaining >= 15:
        try:
            patch, repair_run = model_call(
                {**transport, 'previous_selection': response, 'layout_shortfalls': gaps},
                prompt + '\n这次仅修正分组：多组时每组至少两个不同主体。'
                '依据现有完整观点补选或按真正共同判断重新分组，不改写观点、主体、引文。'
                '不要为了达标只留第一组、抛弃其他有信息增量的观点，也不要把不相干判断硬并。'
                f'现有{len(subjects)}个不同主体，同题每主体只用一次，多组时最多{max(1, len(subjects)//2)}组；'
                '只有3个主体时应考虑一个有真实共同判断的完整段落，不是三段分别编号。'
                '确无合适第二来源时如实保留原有分组和缺口，不能伪造成稿达标。'
                '仍只返回原有选择JSON格式，后续另行全文独立复核。',
                command, workspace, 'synthesis-layout-repair', min(45, remaining), reuse_cache=False)
            candidate = restore(patch)
            remaining_gaps = author_layout_shortfalls(candidate)
            audit.update(repair_response=patch, remaining_shortfalls=remaining_gaps)
            if not remaining_gaps and candidate.get('clusters'):
                result = candidate
                audit['status'] = 'regrouped_pending_independent_review'
            else:
                audit['status'] = 'pending_original_selection_retained'
        except HostModelError as exc:
            if exc.exit_code != 124 or exc.category not in {'', 'timeout'}:
                raise
            repair_run = exc.run
            audit.update(status='pending_original_selection_retained', error=str(exc))
        except (ValueError, TimeoutError) as exc:
            if isinstance(exc, SemanticResponseError):
                repair_run = exc.run
            audit.update(status='pending_original_selection_retained', error=str(exc))
    audit['repair_run'] = repair_run
    result = copy.deepcopy(result)
    result.setdefault('transport_repairs', []).append(audit)
    atomic_write_json(workspace / 'synthesis_layout_repair.json', audit)
    combined = {**run, 'editorial_layout_repair': audit}
    if repair_run:
        combined.update({**repair_run, 'synthesis_initial_run': run,
                         'seconds': run.get('seconds', 0) + repair_run.get('seconds', 0)})
    return result, combined


def enforce_author_layout(decision, prior_source_uses=None):
    """Reserve unresolved length defects and expose, not conceal, group defects.

    Group order is the author's declared priority. This function cannot merge
    groups, invent a second source, or establish a replacement heading. The
    normal independent source and heading reviews must still run afterward.
    """
    result = copy.deepcopy(decision)
    if any(row.get('kind') == 'host_source_order_after_synthesis_interruption'
           for row in result.get('transport_repairs') or [] if isinstance(row, dict)):
        from cwh_semantic_recovery import preserve_extracted_claims
        result, _ = preserve_extracted_claims({'topic': result.get('topic') or result.get('heading') or ''},
            result.get('items') or [], {'kind': 'legacy_ungrouped_cache',
                'reason': 'Old ungrouped draft may be retained as candidates only'})
        return result, {'status': 'legacy_ungrouped_reserves_only', 'formal_prose_emitted': False}
    rules = writing_rules()['viewpoint']
    limit = rules['max_formal_claim_chars']
    groups = {g['key']: [] for g in result.get('clusters') or []}
    changes = []
    used_subjects = set()
    prior_source_uses = prior_source_uses or {}

    def reserve(item, index, claim, reason):
        changes.append({'item_id': item.get('id'), 'claim_index': index,
                        'original_claim': copy.deepcopy(claim), 'reason': reason})
        claim.update(formal_use='reserve', reserve_reason=reason, cluster='__formal_reserve__')

    for item in result.get('items') or []:
        if item.get('decision') != 'eligible':
            continue
        for index, claim in enumerate(item.get('claims') or []):
            if claim.get('formal_use') in {'reserve', 'excluded'} or claim.get('cluster') == '__formal_reserve__':
                continue
            # Do not disguise malformed source/group fields as editorial gaps.
            if claim.get('cluster') not in groups or not isinstance(claim.get('claim'), str):
                continue
            if formal_claim_char_count(claim) > limit:
                reserve(item, index, claim, f'editorial_length_pending:观点超过{limit}字，待忠实精简和独立审核；完整原文与候选保留，不机械截断')
            else:
                groups[claim['cluster']].append((item, index, claim))

    # All author paths (ranked, direct, cached and interrupted synthesis) obey
    # the same source caps. Preserve excess complete claims as audited reserves.
    for group in result.get('clusters') or []:
        for item, index, claim in groups.get(group['key'], []):
            subjects = independent_voice_keys([{'speaker_name': claim.get('speaker'), 'source': item.get('source')}])
            if rules.get('source_max_topic_uses', 1) == 1 and subjects & used_subjects:
                reserve(item, index, claim, 'editorial_same_source_topic_cap:同题同源仅一处，其他完整观点留备选')
            elif any(prior_source_uses.get(s, 0) >= rules.get('source_max_report_uses', 2) for s in subjects):
                reserve(item, index, claim, 'editorial_source_report_cap:同源已达全篇两处上限，完整观点留备选')
            else:
                used_subjects |= subjects

    gaps = author_layout_shortfalls(result)
    if not changes and not gaps:
        return decision, {'status': 'not_needed', 'reserves': []}
    selected_keys = {claim.get('cluster') for item in result.get('items') or []
                     if item.get('decision') == 'eligible' for claim in item.get('claims') or []
                     if claim.get('formal_use') not in {'reserve', 'excluded'}}
    result['clusters'] = [g for g in result.get('clusters') or [] if g['key'] in selected_keys]
    note = '存在长度或分点样本数编辑缺口；过长观点完整留备选，分组问题不触发脚本删组，待作者补选或重组；未达到写作标准。'
    if note not in str(result.get('shortfall_reason') or ''):
        result['shortfall_reason'] = str(result.get('shortfall_reason') or '') + note
    if len(result['clusters']) == 1:
        result['single_cluster_reason'] = str(result.get('single_cluster_reason') or '') + note
    audit = {'status': 'pending_editorial_completion' if gaps else 'reserved_pending_editorial_completion',
             'reserves': changes, 'layout_shortfalls': gaps,
             'original_heading': decision.get('heading'), 'original_clusters': copy.deepcopy(decision.get('clusters')),
             'scope': 'Pre-freeze editorial bookkeeping only; independent claim and heading review still required'}
    entry = {'kind': 'author_layout_selection', **audit}
    if entry not in result.setdefault('transport_repairs', []):
        result['transport_repairs'].append(entry)
    return result, audit
