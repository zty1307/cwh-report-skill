"""Materialize an explicitly priority-ordered native shortlist, not semantics."""
import copy
from cwh_viewpoint_gate import independent_voice_keys
from cwh_writing_rules import writing_rules


def ranked_selection(transport, response):
    if not isinstance(response, dict) or not isinstance(response.get('selected'), list):
        raise ValueError('Ranked selection requires selected groups')
    policy = transport.get('formal_selection') or {}
    if not policy.get('allow_reserve'):
        raise ValueError('Ranked selection requires an auditable reserve policy')
    maximum = policy.get('max_independent_voices')
    if type(maximum) is not int or maximum < 1:
        raise ValueError('Ranked selection requires a positive subject cap')
    if len(response['selected']) > writing_rules()['viewpoint']['bounded_max_formal_clusters']:
        raise ValueError('Ranked selection exceeds the formal cluster cap; select representative distinct judgments instead of listing every subtheme')
    candidates = {row['id']: row for row in transport['candidates']}
    explicit = {}
    for field in ('excluded', 'reserved'):
        rows = response.get(field, [])
        if not isinstance(rows, list):
            raise ValueError('Ranked optional dispositions must be lists')
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {'id', 'reason'}
                or not isinstance(row['id'], str) or row['id'] not in candidates
                or not isinstance(row['reason'], str) or not row['reason'].strip()):
                raise ValueError('Ranked disposition must use an existing claim ID and reason')
            explicit.setdefault(row['id'], []).append((field, row['reason']))
    result = copy.deepcopy(response)
    selected, voices, groups, duplicate_ids, conflicts, capped = set(), set(), [], [], set(), set()
    seen, redundant = set(), set()
    for group in response['selected']:
        if not isinstance(group, dict) or not isinstance(group.get('claim_ids'), list):
            raise ValueError('Ranked group requires claim_ids')
        kept, group_voices = [], set()
        for key in group['claim_ids']:
            if not isinstance(key, str) or key not in candidates:
                raise ValueError('Ranked selection contains an unknown claim ID')
            if key in seen:
                duplicate_ids.append(key)
                continue
            seen.add(key)
            if key in explicit:
                conflicts.add(key)
                continue
            candidate = candidates[key]
            identity = independent_voice_keys([{'speaker_name': candidate.get('speaker'),
                                                'source': candidate.get('source')}])
            if not identity:
                raise ValueError('Ranked candidate has no source identity')
            if identity & group_voices:
                redundant.add(key)
                continue
            if not identity <= voices and len(voices | identity) > maximum:
                capped.add(key)
                continue
            voices |= identity
            group_voices |= identity
            selected.add(key)
            kept.append(key)
        if kept:
            groups.append({**copy.deepcopy(group), 'claim_ids': kept})
    result.update(selected=groups, excluded=[], reserved=[])
    for key in candidates:
        if key in selected:
            continue
        choices = explicit.get(key, [])
        if key not in conflicts and len(choices) == 1 and choices[0][0] == 'excluded':
            result['excluded'].append({'id': key, 'reason': choices[0][1]})
            continue
        reason = ('ranked_selection_conflict:模型同时入选和排除或备选，暂不进入正文' if key in conflicts or len(choices) > 1
                  else 'ranked_subject_cap:按模型声明的重要性排序超出本题主体上限，保留备选' if key in capped
                  else 'ranked_same_subject_group:按模型排序，本组该主体已有更优先的完整论断；本条保留备选，不宣称语义重复' if key in redundant
                  else choices[0][1] if choices else 'ranked_not_selected:模型未列入本稿入选清单，保留候选；未判定证据无效')
        result['reserved'].append({'id': key, 'reason': reason})
    result.setdefault('transport_repairs', []).append({'kind': 'materialized_native_ranked_selection',
        'native_response': copy.deepcopy(response), 'priority_rule': 'Native group order then claim order; first duplicate occurrence wins',
        'selected_subject_count': len(voices), 'max_independent_voices': maximum,
        'duplicate_ids': duplicate_ids, 'conflicting_ids': sorted(conflicts), 'capped_ids': sorted(capped),
        'same_subject_group_reserves': sorted(redundant),
        'scope': 'Mechanical ranked top-subject selection and reserve inventory only; independent source review still mandatory'})
    return result
