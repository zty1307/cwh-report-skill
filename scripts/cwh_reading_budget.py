"""Freeze a bounded full-article reading allocation; no semantic decisions."""
import hashlib
import json
import math
from cwh_pipeline_runtime import atomic_write_json


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def allocate_reading(policy, ceilings, topic_count, remaining_seconds):
    if topic_count < 1 or not math.isfinite(remaining_seconds) or remaining_seconds < 0:
        raise ValueError('Invalid reading budget inputs')
    base_raw = policy['base_monitoring_articles']
    base_web = policy['base_public_pages']
    baseline = policy['baseline_topic_seconds']
    full = policy['expanded_topic_seconds']
    if (type(base_raw) is not int or base_raw < 12 or type(base_web) is not int or base_web < 1
            or not 0 < baseline < full):
        raise ValueError('Invalid reading budget policy; minimum raw coverage is unchanged')
    share = remaining_seconds / topic_count
    fraction = max(0, min(1, (share - baseline) / (full - baseline)))
    bases = [min(base_raw, ceilings[0]), min(base_web, ceilings[1])]
    return [base + math.floor((ceiling - base) * fraction)
            for base, ceiling in zip(bases, ceilings)]


def frozen_reading_allocation(path, plan, ceilings, topic_count, remaining_seconds):
    policy = (plan.get('execution_budget') or {}).get('reading_budget_policy')
    if not policy or not str(plan.get('execution_profile', '')).startswith('bounded_'):
        return tuple(ceilings)
    key = digest({'plan': plan, 'ceilings': ceilings, 'topic_count': topic_count})
    if path.is_file():
        record = json.loads(path.read_text('utf-8'))
        payload = record.get('payload', {})
        if record.get('input_sha256') != key or record.get('payload_sha256') != digest(payload):
            raise ValueError('Reading allocation checkpoint does not match immutable inputs')
        calculated = allocate_reading(policy, ceilings, topic_count, payload['initial_remaining_seconds'])
        if payload.get('limits') != calculated:
            raise ValueError('Reading allocation checkpoint has inconsistent limits')
        return tuple(calculated)
    limits = allocate_reading(policy, ceilings, topic_count, remaining_seconds)
    payload = {'initial_remaining_seconds': remaining_seconds, 'topic_count': topic_count,
               'limits': limits, 'configured_ceilings': list(ceilings),
               'scope': 'Planning heuristic, not a completion promise; intact sources only. '
                        'Unread candidates remain deferred; no source is certified by this allocation.'}
    atomic_write_json(path, {'input_sha256': key, 'payload': payload, 'payload_sha256': digest(payload)})
    return tuple(limits)
