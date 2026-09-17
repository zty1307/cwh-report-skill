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
