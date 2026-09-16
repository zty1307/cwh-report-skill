"""Reject unusable review fields; one bounded genuine body-review retry.

No inferred rationale, verdict, alias, source quote or rewritten native cache.
The retry covers all frozen body claims so its single real reviewer run remains
the provenance of every compiled verdict; already returned headings keep their
original real run and are not silently attributed to this retry.
"""
import copy
import hashlib
import json

VERDICTS = {'fully_supported', 'partially_supported', 'unsupported', 'uncertain'}


def review_field_errors(result, expected_ids, claims=None):
    from domestic_evidence_mapping import has_ambiguous_meeting_reference
    originals = {row['id']: row for row in claims or []}
    rows = result.get('reviews')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Independent review requires a reviews object array')
    ids = [row.get('id') for row in rows]
    if any(not isinstance(identity, str) for identity in ids) or len(set(ids)) != len(ids) or set(ids) != set(expected_ids):
        raise ValueError('Independent reviewer must assess each evidence exactly once')
    errors = []
    for row in rows:
        fields = []
        if not isinstance(row.get('verdict'), str) or row['verdict'] not in VERDICTS:
            fields.append('verdict')
        if not isinstance(row.get('rationale'), str) or not row['rationale'].strip():
            fields.append('rationale')
        revision = row.get('revision')
        original = originals.get(row['id'], {})
        if row.get('verdict') == 'fully_supported' and (original.get('reference_expansion_required') is True
                or has_ambiguous_meeting_reference(original.get('formal_claim'))):
            fields.append('unexpanded_meeting_reference_requires_native_revision')
        if revision is not None:
            if not isinstance(revision, dict) or any(
                not isinstance(revision.get(key), str) or not revision[key].strip()
                for key in ('formal_claim', 'rationale')) or not isinstance(revision.get('verdict'), str) or revision['verdict'] not in VERDICTS:
                fields.append('revision')
        propositions = row.get('propositions') or []
        if not isinstance(propositions, list):
            fields.append('propositions')
            propositions = []
        for proposition in propositions:
            if not isinstance(proposition, dict) or not isinstance(proposition.get('rationale'), str) or not proposition['rationale'].strip():
                fields.append('propositions.rationale')
                break
        if fields:
            errors.append({'id': row['id'], 'invalid_fields': fields})
    return errors


def retry_invalid_review_fields(request, result, run, prompt, command, workspace, timeout):
    from cwh_host_research import semantic_json
    ids = [claim['id'] for claim in request['claims']]
    errors = review_field_errors(result, ids, request['claims'])
    if not errors:
        return result, run
    if timeout < 15:
        raise ValueError('Invalid independent review fields with no retry budget: ' + json.dumps(errors, ensure_ascii=False))
    # Headings are not part of this body-field recovery. Every new body verdict
    # must genuinely be rechecked, rather than a script restamping old verdicts.
    packet = {key: copy.deepcopy(value) for key, value in request.items() if key != 'headings'}
    packet['field_validation_feedback'] = errors
    corrected, retry_run = semantic_json(packet,
        prompt + '\n此前正文审核含空值或非法字段，尚未通过字段门禁。只返回reviews，覆盖本输入全部claim ID一次，'
        '按每条冻结excerpt重新核验并给出非空字符串rationale；可以修正verdict，不强制维持此前支持结论。'
        'revision有值时完整填写formal_claim、verdict、rationale；确无可支持观点可以uncertain、revision=null并解释。'
        '不审核标题，不编造缺失论据。遇unexpanded_meeting_reference反馈，原句的会议指称未展开，不能直接fully_supported；'
        '须根据sources标题或开头确认实际会议名称，在revision中由你明确名称，原文论据仍只取同条excerpt。'
        '无法确认就uncertain且revision=null，不得由report_agenda猜测。', command, workspace,
        'independent-review-field-retry', min(45, timeout))
    remaining = review_field_errors(corrected, ids, request['claims'])
    if remaining:
        raise ValueError('Independent review field retry still invalid: ' + json.dumps(remaining, ensure_ascii=False))
    combined = copy.deepcopy(result)
    combined['reviews'] = copy.deepcopy(corrected['reviews'])
    if combined.get('heading_reviews'):
        for heading in combined['heading_reviews']:
            heading['reviewer_run_id'] = run['session_id']
        combined['heading_original_run'] = copy.deepcopy(run)
    combined['review_field_retry'] = {
        'original_run': copy.deepcopy(run), 'retry_run': copy.deepcopy(retry_run),
        'invalid_fields': errors, 'original_result_sha256': hashlib.sha256(
            json.dumps(result, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        'scope': 'One genuine frozen body-review retry; no heading re-review, inferred fields or changed stage budget'}
    return combined, retry_run
