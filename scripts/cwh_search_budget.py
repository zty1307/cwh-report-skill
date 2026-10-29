"""Auditable query-cap stopping is not evidence that research is saturated."""
from cwh_model_contract import execution_profile


def query_budget_evidence(saturation, profile):
    if profile not in {'bounded_40m', 'bounded_45m', 'bounded_60m'}:
        return None
    if saturation.get('stop_reason') != 'coverage_minimum_then_one_zero_new_round_or_budget_exhausted':
        return None
    _, settings = execution_profile(profile)
    cap = int(settings['research']['max_query_executions_per_topic'])
    allocated = cap
    if settings['research'].get('adaptive_web_policy'):
        allocated = saturation.get('allocated_query_limit', cap)
        base = settings['research']['adaptive_web_policy']['base_queries']
        if type(allocated) is not int or not base <= allocated <= cap:
            return None
    rows = [q for r in saturation.get('rounds') or [] for q in r.get('executions') or []
            if q.get('route') in {'stable_registry', 'open_web', 'public_platform'}]
    if len(rows) < allocated or len({q.get('query_id') for q in rows}) != len(rows):
        return None
    if len({str(q.get('query') or '').strip() for q in rows}) < allocated:
        return None
    for row in rows:
        if (not all(row.get(k) for k in ('query_id', 'query', 'backend', 'executed_at'))
                or row.get('status') not in {'completed', 'access_failed'}
                or not isinstance(row.get('result_urls'), list)):
            return None
    result = {'basis': 'executed_unique_query_cap', 'execution_profile': profile,
            'configured_max_queries': cap, 'executed_query_ids': [q['query_id'] for q in rows],
            'saturation_proven': False}
    if allocated != cap:
        result.update(basis='executed_allocated_query_budget', allocated_query_limit=allocated)
    return result


def valid_query_budget_stop(saturation, profile):
    expected = query_budget_evidence(saturation, profile)
    return bool(expected and saturation.get('completed') is False
                and saturation.get('budget_stop') == expected)
