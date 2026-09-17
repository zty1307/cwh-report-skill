"""Reject unusable review fields; one bounded genuine local-review retry.

No inferred rationale, verdict, alias, source quote or rewritten native cache.
Only affected frozen claims are retried. Unchanged verdicts and headings retain
their original real run; no unrelated source re-reading or silent restamping.
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
    # Preserve global IDs and full excerpts, but never re-review unrelated claims
    # merely because another row omitted a field or a meeting reference.
    packet = {key: copy.deepcopy(value) for key, value in request.items() if key != 'headings'}
    retry_ids = {row['id'] for row in errors}
    packet['claims'] = [row for row in packet['claims'] if row['id'] in retry_ids]
    source_ids = {row.get('source_id') for row in packet['claims']}
    if all(row.get('source_id') for row in packet['claims']):
        packet['sources'] = [row for row in packet.get('sources', []) if row['id'] in source_ids]
    packet['field_validation_feedback'] = errors
    corrected, retry_run = semantic_json(packet,
        prompt + '\n此前正文审核含空值或非法字段，尚未通过字段门禁。只返回reviews，覆盖本输入全部claim ID一次，'
        '按每条冻结excerpt重新核验并给出非空字符串rationale；可以修正verdict，不强制维持此前支持结论。'
        'revision有值时完整填写formal_claim、verdict、rationale；确无可支持观点可以uncertain、revision=null并解释。'
        '不审核标题，不编造缺失论据。遇unexpanded_meeting_reference反馈，原句的会议指称未展开，不能直接fully_supported；'
        '须根据sources标题或开头确认实际会议名称，在revision中由你明确名称，原文论据仍只取同条excerpt。'
        '无法确认就uncertain且revision=null，不得由report_agenda猜测。'
        '对反馈列出的未展开指称，原句verdict只能partially_supported或uncertain；'
        '确认后必须把实际会议全称写入revision.formal_claim，仅在rationale说明语境明确不算修正文。'
        '输入旧heading本身可能错误，不能据其把报告会议改成另一场会议。', command, workspace,
        'independent-review-field-retry', min(45, timeout))
    remaining = review_field_errors(corrected, retry_ids, packet['claims'])
    quarantined = []
    if (remaining and request.get('delivery_policy') == 'deliver_available_with_gaps'
            and all(row['invalid_fields'] == ['unexpanded_meeting_reference_requires_native_revision'] for row in remaining)):
        # A model's positive verdict cannot waive this mechanical publication
        # gate. Preserve its real verdict verbatim, but do not publish the claim.
        corrected = copy.deepcopy(corrected)
        failed = {row['id'] for row in remaining}
        for row in corrected['reviews']:
            if row['id'] not in failed:
                continue
            original_review = copy.deepcopy(row)
            row.update(verdict='uncertain', revision=None,
                rationale='宿主字面门禁：一次原生补核后仍未在正文展开会议指称，暂不进入正文；此为发布限制，不是模型的语义否定结论。',
                host_reference_gate={'origin': 'deterministic_reference_gate', 'native_review': original_review,
                    'actual_native_run': copy.deepcopy(retry_run)})
            row.pop('propositions', None)
            quarantined.append(row['id'])
        remaining = review_field_errors(corrected, retry_ids, packet['claims'])
    if remaining:
        raise ValueError('Independent review field retry still invalid: ' + json.dumps(remaining, ensure_ascii=False))
    combined = copy.deepcopy(result)
    replacements = {row['id']: row for row in corrected['reviews']}
    combined['reviews'] = [copy.deepcopy(replacements.get(row['id'], row)) for row in result['reviews']]
    if review_field_errors(combined, ids, request['claims']):
        raise ValueError('Local review retry left invalid fields')
    if combined.get('heading_reviews'):
        for heading in combined['heading_reviews']:
            heading['reviewer_run_id'] = run['session_id']
        combined['heading_original_run'] = copy.deepcopy(run)
    combined['review_field_retry'] = {
        'original_run': copy.deepcopy(run), 'retry_run': copy.deepcopy(retry_run),
        'retried_claim_ids': [row['id'] for row in packet['claims']],
        'invalid_fields': errors, 'original_result_sha256': hashlib.sha256(
            json.dumps(result, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        'scope': 'One genuine affected-claim retry; other verdicts and full excerpts unchanged; no added stage budget'}
    if quarantined:
        combined['review_field_retry']['host_reference_quarantines'] = quarantined
    return combined, retry_run
