"""Bounded independent body review with intact excerpts and real per-row runs."""
import copy
import time
import uuid
from cwh_pipeline_runtime import atomic_write_json
from cwh_pipeline_runtime import utc_now
from cwh_host_research import HostModelError, SemanticResponseError
from cwh_semantic_recovery import interruption, POLICY
from cwh_review_fields import review_field_errors, retry_invalid_review_fields


def partition_review_packet(packet, maximum=8):
    if type(maximum) is not int or maximum < 1:
        raise ValueError('Invalid body-review batch size')
    claims = packet['claims']
    identities = [row['id'] for row in claims]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate frozen claim IDs')
    parents = {identity: identity for identity in identities}
    def root(identity):
        while parents[identity] != identity:
            identity = parents[identity]
        return identity
    # Cross-topic duplicate/span comparisons must see both complete claims in
    # one call. Large connected components stay intact rather than truncated.
    for key in ('cross_topic_exact_duplicates', 'cross_topic_shared_source_spans'):
        for group in packet.get(key, []):
            ids = group['claim_ids']
            if any(identity not in parents for identity in ids):
                raise ValueError('Comparison references unknown claim')
            for identity in ids[1:]:
                parents[root(identity)] = root(ids[0])
    components = {}
    for row in claims:
        components.setdefault(root(row['id']), []).append(row)
    groups, current = [], []
    for component in components.values():
        if current and len(current) + len(component) > maximum:
            groups.append(current)
            current = []
        current.extend(component)
    if current:
        groups.append(current)
    parts = []
    for rows in groups:
        part = {k: copy.deepcopy(v) for k, v in packet.items()
                if k not in {'claims', 'sources', 'headings', 'cross_topic_exact_duplicates', 'cross_topic_shared_source_spans'}}
        wanted = {r['id'] for r in rows}
        sources = {r['source_id'] for r in rows}
        part['claims'] = copy.deepcopy(rows)
        part['sources'] = [copy.deepcopy(r) for r in packet['sources'] if r['id'] in sources]
        for key in ('cross_topic_exact_duplicates', 'cross_topic_shared_source_spans'):
            part[key] = [copy.deepcopy(r) for r in packet.get(key, []) if set(r['claim_ids']) & wanted]
        parts.append(part)
    return parts


def review_body_batches(packet, prompt, command, workspace, deadline, model_call):
    parts = partition_review_packet(packet)
    reviews, origins, records = {}, {}, []
    last_run = {'session_id': 'host-empty-review-' + str(uuid.uuid4()), 'completed_at': utc_now(), 'model_invoked': False}
    for number, part in enumerate(parts, 1):
        remaining = deadline - time.monotonic() - 35  # Reserve the actual heading pass.
        share = remaining / (len(parts) - number + 1)
        local_deadline = time.monotonic() + min(180, share)
        folder = workspace / f'body-review-{number}'
        folder.mkdir(parents=True, exist_ok=True)
        atomic_write_json(folder / 'request.json', part)
        try:
            if share < 15 and not (folder / 'independent-body-review.cache.json').is_file():
                raise TimeoutError('No remaining frozen body-review batch budget')
            result, run = model_call(part, prompt + '\n本次只审核本批claims，不审核标题。保持输入短ID，不重新编号；'
                '每条从自己的excerpt_segments逐项找依据，不能用另一条摘录替代。',
                command, folder, 'independent-body-review',
                max(10, min(150, share * .80)) if share >= 15 else 0, reuse_cache=True)
        except (HostModelError, SemanticResponseError, TimeoutError) as exc:
            if packet.get('delivery_policy') != POLICY:
                raise
            failure = interruption(exc)
            run = {'session_id': 'host-unreviewed-' + str(uuid.uuid4()), 'completed_at': utc_now(),
                   'model_invoked': False, 'interruption': failure}
            # A host uncertainty record is not a model review. Retention removes
            # these rows before formal certification, preserving the reason.
            result = {'reviews': [{'id': row['id'], 'verdict': 'uncertain', 'revision': None,
                'rationale': '独立核验未完成，暂不进入正式报告；不能据此认定原文不支持观点。',
                'host_unreviewed': copy.deepcopy(failure)} for row in part['claims']]}
        # Model-supplied host provenance is never trusted.
        for key in ('review_field_retry', 'heading_original_run', 'heading_repair_run', 'heading_repair_runs'):
            result.pop(key, None)
        result.pop('heading_reviews', None)
        if run.get('model_invoked') is False:
            actual = run
        else:
            for row in result.get('reviews') or []:
                if isinstance(row, dict):
                    row.pop('host_unreviewed', None)
            try:
                result, actual = retry_invalid_review_fields(part, result, run, prompt, command, folder,
                                                            local_deadline - time.monotonic())
            except (HostModelError, SemanticResponseError, TimeoutError, ValueError) as exc:
                if packet.get('delivery_policy') != POLICY:
                    raise
                failure = interruption(exc if isinstance(exc, (HostModelError, SemanticResponseError, TimeoutError))
                                       else SemanticResponseError(str(exc), run))
                atomic_write_json(folder / 'incomplete_review.json', {'result': result, 'run': run, 'interruption': failure})
                # Keep unaffected native rows when the returned ID set is valid.
                try:
                    invalid = {e['id'] for e in review_field_errors(result, [r['id'] for r in part['claims']], part['claims'])}
                    kept = {r['id']: r for r in result['reviews'] if r['id'] not in invalid}
                except ValueError:
                    kept = {}
                host_run = {'session_id': 'host-unreviewed-' + str(uuid.uuid4()), 'completed_at': utc_now(),
                            'model_invoked': False, 'interruption': failure}
                for row in part['claims']:
                    if row['id'] not in kept:
                        kept[row['id']] = {'id': row['id'], 'verdict': 'uncertain', 'revision': None,
                            'rationale': '独立核验输出未通过格式校验，本条保留待审。', 'host_unreviewed': copy.deepcopy(failure)}
                result = {'reviews': [kept[r['id']] for r in part['claims']]}
                for row in result['reviews']:
                    if row.get('host_unreviewed'):
                        origins[row['id']] = copy.deepcopy(host_run)
                actual = run
        errors = review_field_errors(result, [r['id'] for r in part['claims']], part['claims'])
        if errors:
            raise ValueError('Frozen body batch has invalid review fields')
        retry = result.get('review_field_retry') or {}
        for row in result['reviews']:
            identity = row['id']
            if identity in reviews:
                raise ValueError('Body batch repeated a reviewed claim')
            reviews[identity] = copy.deepcopy(row)
            origins.setdefault(identity, copy.deepcopy(actual if identity in retry.get('retried_claim_ids', []) else run))
        records.append({'claim_ids': [r['id'] for r in part['claims']], 'original_run': copy.deepcopy(run),
                        'review_field_retry': copy.deepcopy(retry) or None})
        last_run = actual
        atomic_write_json(workspace / 'body_review_batches.json', {'batches': records,
            'completed_claim_ids': list(reviews), 'scope': 'Actual independent batches; unreviewed claims not certified'})
    if set(reviews) != {r['id'] for r in packet['claims']}:
        raise ValueError('Incomplete body-review batch coverage')
    return {'reviews': [reviews[r['id']] for r in packet['claims']]}, last_run, origins, records
