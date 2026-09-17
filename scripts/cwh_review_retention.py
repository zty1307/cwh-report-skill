"""Retain certified claims after real rejection; never guess or waive source gates."""
import copy
import hashlib
import json
from domestic_evidence_mapping import validate_analysis_mapping, has_ambiguous_meeting_reference
from normalize_cwh_analysis import normalize_analysis
from cwh_available_delivery import prepare_available_delivery
from cwh_review_repair import evidence_rows


def retain_reviewed_content(original, initial):
    rows = {ev['evidence_id']: (topic, ev) for topic, ev in evidence_rows(original)}
    reviews = {r['evidence_id']: r for r in initial['reviews']}
    if len(reviews) != len(initial['reviews']) or set(reviews) != set(rows):
        raise ValueError('Retention must start from complete independent review coverage')
    result = copy.deepcopy(original)
    current = {ev['evidence_id']: ev for _, ev in evidence_rows(result)}
    actions, rejected = [], set()
    for identity, review in reviews.items():
        if review['verdict'] == 'fully_supported':
            continue
        revision = review.get('revision')
        usable = (isinstance(revision, dict) and revision.get('verdict') == 'fully_supported'
                  and isinstance(revision.get('formal_claim'), str) and revision['formal_claim'].strip()
                  and isinstance(revision.get('rationale'), str) and revision['rationale'].strip())
        issues = []
        if usable:
            trial = copy.deepcopy(result)
            ev = next(ev for _, ev in evidence_rows(trial) if ev['evidence_id'] == identity)
            ev['formal_claim'] = revision['formal_claim'].strip()
            trial = normalize_analysis(trial)
            issues = [i for i in validate_analysis_mapping(trial, require_semantic_review=False)['issues']
                      if i.get('evidence_id') == identity]
            usable = not issues
            if has_ambiguous_meeting_reference(revision['formal_claim']):
                usable = False
                issues.append({'code': 'ambiguous_meeting_reference', 'evidence_id': identity,
                               'message': 'Reviewer revision still contains an unexpanded meeting reference'})
        action = {'evidence_id': identity, 'original_review': copy.deepcopy(review),
                  'action': 'narrowed' if usable else 'excluded', 'draft_gate_issues': issues}
        if usable:
            current[identity]['formal_claim'] = revision['formal_claim'].strip()
        else:
            rejected.add(identity)
            action['excluded_evidence'] = copy.deepcopy(rows[identity][1])
        actions.append(action)
    affected_topics = {rows[r['evidence_id']][0] for r in actions}
    for topic in result['viewpoints']['by_topic']:
        if topic['topic'] not in affected_topics:
            continue
        for cluster in topic['clusters']:
            cluster['evidence'] = [e for e in cluster['evidence'] if e['evidence_id'] not in rejected]
            cluster.pop('thin_cluster_exception', None)
        topic.pop('evidence_shortfall', None)
        topic.pop('single_cluster_exception', None)
    retained_candidates = {(topic, ev['candidate_id']) for topic, ev in evidence_rows(result)}
    candidate_actions = []
    for pool in result['research_audit']['domestic_media_research']['candidate_pool_by_topic']:
        for candidate in pool['candidates']:
            failed = [a for a in actions if a['action'] == 'excluded'
                      and rows[a['evidence_id']][0] == pool['topic']
                      and rows[a['evidence_id']][1]['candidate_id'] == candidate['candidate_id']]
            if failed and (pool['topic'], candidate['candidate_id']) not in retained_candidates:
                candidate_actions.append({'topic': pool['topic'], 'candidate_id': candidate['candidate_id'],
                                          'original_candidate': copy.deepcopy(candidate)})
                candidate['decision'] = 'excluded'
                candidate['decision_reason'] = '独立审核未取得可通过原文门禁的修订；仅排除正式选材，原始候选全文保留。'
    result['research_audit']['independent_review_retention'] = {
        'reviewer_run_id': initial['reviewer_run_id'], 'actions': actions,
        'candidate_actions': candidate_actions,
        'scope': 'Actual rejected claims only; not zero-result research or semantic certification by controller'}
    unreviewed = [a['evidence_id'] for a in actions if a['original_review'].get('host_unreviewed')]
    if unreviewed:
        result.setdefault('metadata', {}).setdefault('independent_review_gaps', []).append({
            'unreviewed_evidence_ids': unreviewed,
            'notice': f'{len(unreviewed)}条已提取观点未完成独立核验，保留原文和草稿，不进入本次正式正文。'})
    result = normalize_analysis(prepare_available_delivery(result))
    return result, actions


def retention_packet(repaired, initial, actions, run, source_hash):
    from run_cwh_compiled_worker import compile_review
    first = {r['evidence_id']: r for r in initial['reviews']}
    narrowed = {a['evidence_id'] for a in actions if a['action'] == 'narrowed'}
    raw = []
    for index, (_, ev) in enumerate(evidence_rows(repaired), 1):
        earlier = first[ev['evidence_id']]
        if ev['evidence_id'] in narrowed:
            row = {'id': f'e{index}', 'verdict': 'fully_supported',
                   'rationale': earlier['revision']['rationale']}
        else:
            row = copy.deepcopy(earlier)
            for key in ('evidence_id', 'reviewed_by', 'reviewed_at', 'reviewer_run_id'):
                row.pop(key, None)
            row['id'] = f'e{index}'
        raw.append(row)
    final = compile_review(repaired, {'reviews': raw}, run, source_hash)
    for row in final['reviews']:
        earlier = first[row['evidence_id']]
        row.update(reviewed_by=earlier['reviewed_by'], reviewed_at=earlier['reviewed_at'],
                   reviewer_run_id=earlier.get('reviewer_run_id') or initial['reviewer_run_id'])
    final['reviewer_run_ids'] = list(initial.get('reviewer_run_ids') or [initial['reviewer_run_id']])
    final['repair_provenance'] = {
        'mode': 'reviewer_retention_v1',
        'original_source_bundle_sha256': initial['source_bundle_sha256'],
        'repaired_evidence_ids': sorted(a['evidence_id'] for a in actions),
        'earlier_review_sha256': hashlib.sha256(json.dumps(initial, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        'excluded_evidence_ids': sorted(a['evidence_id'] for a in actions if a['action'] == 'excluded'),
        'heading_review_status': 'not_carried_forward_after_claim_changes'}
    return final


def validate_retention(original, repaired, initial, combined):
    expected, actions = retain_reviewed_content(original, initial)
    if expected != repaired:
        raise ValueError('Retention changed frozen sources, accepted content or actual rejection audit')
    excluded = {a['evidence_id'] for a in actions if a['action'] == 'excluded'}
    if set(combined['repair_provenance'].get('excluded_evidence_ids') or []) != excluded:
        raise ValueError('Retention exclusion audit differs from actual rejected claims')
    first = {r['evidence_id']: r for r in initial['reviews']}
    final = {r['evidence_id']: r for r in combined['reviews']}
    wanted = {ev['evidence_id'] for _, ev in evidence_rows(repaired)}
    if len(final) != len(combined['reviews']) or set(final) != wanted:
        raise ValueError('Retained review coverage differs from retained evidence')
    for identity, row in final.items():
        earlier = first[identity]
        if earlier['verdict'] == 'fully_supported':
            if row != {**earlier, 'reviewer_run_id': earlier.get('reviewer_run_id') or initial['reviewer_run_id']}:
                raise ValueError('Retention rewrote an accepted verdict or real reviewer')
        else:
            revision = earlier['revision']
            ev = next(ev for _, ev in evidence_rows(repaired) if ev['evidence_id'] == identity)
            if (row['verdict'] != 'fully_supported' or row['rationale'] != revision['rationale']
                    or ev['formal_claim'] != revision['formal_claim'].strip()
                    or row['reviewer_run_id'] != (earlier.get('reviewer_run_id') or initial['reviewer_run_id'])
                    or row['reviewed_by'] != earlier['reviewed_by'] or row['reviewed_at'] != earlier['reviewed_at']):
                raise ValueError('Retention changed independent narrowing certification')
