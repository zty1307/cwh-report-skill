"""Host-owned interruption records; never substitute a successful AI review."""
import copy
import uuid
from cwh_host_research import HostModelError, SemanticResponseError
from cwh_pipeline_runtime import utc_now


POLICY = 'deliver_available_with_gaps'


def valid_interruption(row):
    run = row.get('actual_run') or {}
    return (run.get('exit_code') == 124
        or (row.get('kind') == 'invalid_model_response' and bool(run.get('session_id')))
        or (row.get('kind') == 'budget_exhausted_before_call' and run.get('model_invoked') is False))


def valid_raw_deferrals(review, expected, reviewed):
    rows = review.get('deferred_records') or []
    ids = [r.get('record_id') for r in rows]
    return (review.get('delivery_policy') == POLICY and len(ids) == len(set(ids))
            and set(ids) == set(expected) - set(reviewed) and not set(reviewed) - set(expected)
            and all(valid_interruption(row) for row in rows))


def valid_partial_foreign(audit):
    """Accept an honestly incomplete artifact, never a fabricated successful search."""
    import hashlib
    import json
    from pathlib import Path
    observations = audit.get('search_observations') or {}
    queries = observations.get('queries') or []
    run = observations.get('host_run') or {}
    log = Path(str(run.get('log') or ''))
    if not (audit.get('delivery_policy') == POLICY and audit.get('collection_status') == 'partial_completed'
            and audit.get('collection_completed') is False and audit.get('notice')
            and run.get('session_id') and run.get('exit_code') in (0, 124) and log.is_file()
            and observations.get('log_sha256') == hashlib.sha256(log.read_bytes()).hexdigest()):
        return False
    if not queries or not any(q.get('kind') == 'comments' for q in queries):
        return False
    registry = json.loads((Path(__file__).resolve().parents[1] / 'config' / 'source_registry.v1.json').read_text('utf-8-sig'))
    expected = {r['id'] for r in registry['sources'] if r.get('must_check') and r.get('tier') == 'overseas_media'}
    if audit.get('registry_version') != registry.get('version') or not expected <= {q.get('source_id') for q in queries}:
        return False
    return (all(q.get('query') and q.get('status') in {'completed', 'access_failed'}
                and (q.get('status') != 'access_failed' or q.get('blocker')) for q in queries)
            and all(valid_interruption(row) for row in audit.get('review_deferred_records') or []))


def deferred_hotwords(failure):
    return {'status': 'review_deferred', 'review_method': 'host_unreviewed', 'method': 'host_unreviewed',
            'delivery_policy': POLICY, 'selected': [], 'second_pass_completed': False,
            'interruption': copy.deepcopy(failure),
            'notice': '热词审核尚未完成，本稿暂不生成词云；不代表没有相关热词。'}


def is_deferred_hotwords(data):
    return (data.get('delivery_policy') == POLICY and data.get('status') == 'review_deferred'
            and data.get('review_method') == 'host_unreviewed' and data.get('selected') == []
            and data.get('second_pass_completed') is False
            and bool(data.get('notice')) and valid_interruption(data.get('interruption') or {}))


def interruption(exc):
    if isinstance(exc, HostModelError):
        if exc.exit_code != 124 or exc.category not in {'', 'timeout'}:
            raise exc
        return {'kind': 'model_timeout', 'reason': str(exc),
                'actual_run': copy.deepcopy(exc.run or {})}
    if isinstance(exc, SemanticResponseError):
        return {'kind': 'invalid_model_response', 'reason': str(exc),
                'actual_run': copy.deepcopy(exc.run or {})}
    if isinstance(exc, TimeoutError):
        return {'kind': 'budget_exhausted_before_call', 'reason': str(exc),
                'actual_run': {'model_invoked': False}}
    raise exc


def defer_reading(ids, failure):
    return ([{'id': value, **copy.deepcopy(failure)} for value in ids],
            [{'id': value, 'decision': 'excluded', 'claims': [],
              'reason': '本批未取得完成的模型阅读结果，原文保留待审；不判断其是否含独立解读。'} for value in ids])


def preserve_extracted_claims(packet, decisions, failure):
    """Preserve extracted material as candidates, never as ungrouped prose."""
    choices = copy.deepcopy(decisions)
    reservations = []
    for row in choices:
        for index, claim in enumerate(row.get('claims') or []):
            if claim.get('formal_use') in {'reserve', 'excluded'}:
                continue
            reason = 'editorial_grouping_pending:尚未完成观点选择、分组与标题，只存工作台候选，不拼接进入正文'
            reservations.append({'item_id': row.get('id'), 'claim_index': index,
                                 'native_claim': copy.deepcopy(claim), 'reason': reason})
            claim.update(formal_use='reserve', reserve_reason=reason, cluster='__formal_reserve__')
    note = '本题观点分组尚未完成，已摘录材料完整保留在工作台候选区；正文不按来源顺序拼接，不冒充成文完成。'
    result = {'items': choices, 'heading': '', 'clusters': [],
              'shortfall_reason': note, 'single_cluster_reason': note,
              'transport_repairs': [{'kind': 'candidates_preserved_after_synthesis_interruption',
                  'reservations': reservations, 'formal_prose_emitted': False, **failure}]}
    run = {'session_id': str(uuid.uuid4()), 'completed_at': utc_now(), 'seconds': 0,
           'model_invoked': False, 'transport': 'candidate_reserve_pending_native_grouping',
           'synthesis_interruption': copy.deepcopy(failure)}
    return result, run
