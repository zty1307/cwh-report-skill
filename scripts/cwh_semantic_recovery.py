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
    """Keep native extraction in source order under a neutral topic label.

    No host-written stance, semantic cluster, priority, or certification.
    Excess voices remain reserves with an explicitly mechanical reason.
    """
    choices = copy.deepcopy(decisions)
    limit = (packet.get('formal_selection') or {}).get('max_independent_voices') or 12
    voices = set()
    for row in choices:
        for claim in row.get('claims') or []:
            key = (claim.get('speaker'), claim.get('role'), claim.get('speaker_type'))
            claim['cluster'] = 'source_order'
            if key not in voices and len(voices) >= limit:
                claim.update(formal_use='reserve', reserve_reason='分组调用未完成，按原文提取顺序保留至本稿人数上限；未进行模型优先级排序。')
            else:
                voices.add(key)
    note = '模型分组未完成，暂按来源顺序保留已提取判断；各判断仍须独立核验，未生成主题立场标题。'
    result = {'items': choices, 'heading': packet['topic'],
              'clusters': [{'key': 'source_order', 'heading': packet['topic'], 'thin_reason': note}],
              'shortfall_reason': note, 'single_cluster_reason': note,
              'transport_repairs': [{'kind': 'host_source_order_after_synthesis_interruption', **failure}]}
    run = {'session_id': str(uuid.uuid4()), 'completed_at': utc_now(), 'seconds': 0,
           'model_invoked': False, 'transport': 'source_order_without_semantic_grouping',
           'synthesis_interruption': copy.deepcopy(failure)}
    return result, run
