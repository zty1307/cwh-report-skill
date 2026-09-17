"""Bounded native hotword review with intact per-term evidence and a global pass."""
import copy
import math
import time
from cwh_evidence_window_transport import pool_hotword_windows
from cwh_pipeline_runtime import atomic_write_json
from cwh_hotword_pipeline import normalize_text


class MissingHotwordWitness(ValueError):
    """A native extension has no literal witness in the supplied source windows."""


def subset_packet(packet, candidates):
    result = copy.deepcopy(packet)
    terms = {row['term'] for row in candidates}
    result['candidates'] = copy.deepcopy(candidates)
    result['candidate_source_windows'] = [copy.deepcopy(row) for row in packet['candidate_source_windows']
                                          if row['term'] in terms]
    refs = {ref for row in candidates for ref in row.get('sample_url_refs', [])}
    refs.update(window['url_ref'] for row in result['candidate_source_windows']
                for window in row['source_windows'])
    result['source_urls'] = {key: value for key, value in packet['source_urls'].items() if key in refs}
    return result


def partition_candidates(packet, max_candidates=40):
    if type(max_candidates) is not int or max_candidates < 1:
        raise ValueError('Invalid hotword batch size')
    groups = {}
    for row in packet['candidates']:
        hits = row.get('topic_hits') or []
        topic = row.get('topic_index') or (hits[0] if hits else 'unassigned')
        groups.setdefault(topic, []).append(row)
    return [rows[offset:offset + max_candidates] for rows in groups.values()
            for offset in range(0, len(rows), max_candidates)]


def retain_native_extensions(packet, selected):
    """Keep native new phrases only with a literal retained-source witness; no invented counts."""
    result = copy.deepcopy(packet)
    known = {row['term'] for row in result['candidates']}
    for row in selected:
        term = row['term']
        if term in known:
            continue
        needles = [term, *row.get('evidence_aliases', [])]
        if any(not isinstance(value, str) or not value.strip() for value in needles):
            raise ValueError('Invalid native hotword evidence aliases')
        windows = []
        for entry in packet['candidate_source_windows']:
            for window in entry['source_windows']:
                if any(normalize_text(value) in normalize_text(window['excerpt']) for value in needles) and window not in windows:
                    windows.append(copy.deepcopy(window))
        if not windows:
            raise MissingHotwordWitness(f'Native added hotword has no literal retained-source witness: {term}')
        result['candidates'].append({'term': term, 'topic_hits': row.get('topic_hits', []),
                                    'origin': 'native_first_pass_extension; counts require full-source gate'})
        result['candidate_source_windows'].append({'term': term, 'source_windows': windows})
        known.add(term)
    return result


def review_hotword_batches(packet, prompt_rules, command, workspace, deadline, model_call,
                           feedback=''):
    """One native pass per partition, then native global deduplication. No host selection."""
    from run_cwh_inline_review import normalize_hotword_transport, normalize_topic_hit_transport
    batches = partition_candidates(packet)
    records, chosen, quarantined, deferred = [], [], [], []
    extended = copy.deepcopy(packet)
    target = int(packet.get('target_term_count') or 48)

    def call(part, prompt, name, remaining_calls):
        atomic_write_json(workspace / f'{name}.packet.json', part)
        remaining = deadline - time.monotonic()
        if remaining < 10:
            from cwh_host_research import HostModelError
            raise HostModelError('Hotword batch deadline exhausted', 124)
        timeout = min(90, remaining / remaining_calls)
        try:
            result, run = model_call(pool_hotword_windows(part), prompt, command, workspace,
                                     name, timeout, reuse_cache=True)
        except Exception as exc:
            records.append({'name': name, 'failed': True, 'error': str(exc), 'run': getattr(exc, 'run', None)})
            atomic_write_json(workspace / 'hotword_batch_runs.json', records)
            raise
        records.append({'name': name, 'candidate_count': len(part['candidates']), 'run': run})
        atomic_write_json(workspace / 'hotword_batch_runs.json', records)
        if result.get('blocker'):
            raise ValueError('Native hotword batch returned a blocker')
        result = normalize_topic_hit_transport(part, normalize_hotword_transport(result), 'hotword')
        selected = result.get('selected')
        if not isinstance(selected, list) or any(not isinstance(row, dict) or not isinstance(row.get('term'), str)
                                                  for row in selected):
            raise ValueError('Hotword batch selected must be an array')
        if len({row['term'] for row in selected}) != len(selected):
            raise ValueError('Hotword batch repeated an exact term')
        accepted = []
        for row in selected:
            try:
                retain_native_extensions(part, [row])
            except MissingHotwordWitness as exc:
                if packet.get('delivery_policy') != 'deliver_available_with_gaps':
                    raise
                quarantined.append({'batch': name, 'native_run': copy.deepcopy(run),
                                    'native_selection': copy.deepcopy(row), 'reason': str(exc),
                                    'origin': 'literal_source_witness_gate; not semantic rejection'})
            else:
                accepted.append(row)
        if quarantined:
            atomic_write_json(workspace / 'hotword_source_quarantine.json', quarantined)
        result['selected'] = accepted
        return result

    for number, rows in enumerate(batches, 1):
        part = subset_packet(packet, rows)
        part['minimum_term_count'] = 0
        part['target_term_count'] = math.ceil(target * len(rows) / len(packet['candidates'])) + 2
        part['batch_scope'] = 'Disjoint candidate partition; all original topic indices and exact source windows retained.'
        prompt = (prompt_rules + '\n这是分组初审，不是全表最终审核；仅审核本组候选。数量只作目标，无合格词可返回selected:[]。'
                  '返回原review_output_shape的热词字段，保留真实证据，不因全局数量要求在本组凑数。')
        if feedback:
            prompt += '\n上次真实校验反馈：' + feedback
        from cwh_host_research import HostModelError, SemanticResponseError
        try:
            reviewed = call(part, prompt, f'hotword-batch-{number}', len(batches) - number + 2)
        except (HostModelError, ValueError, TypeError, KeyError) as exc:
            if packet.get('delivery_policy') != 'deliver_available_with_gaps':
                raise
            from cwh_semantic_recovery import interruption
            if not isinstance(exc, (HostModelError, SemanticResponseError)):
                actual = next((r.get('run') for r in reversed(records) if r.get('name') == f'hotword-batch-{number}'), None)
                if not actual:
                    raise
                exc = SemanticResponseError(str(exc), actual)
            if isinstance(exc, HostModelError) and exc.exit_code == 124 and not exc.run:
                failure = interruption(TimeoutError(str(exc)))
            else:
                failure = interruption(exc)
            deferred.append({'batch': number, 'terms': [r['term'] for r in rows], **failure})
            atomic_write_json(workspace / 'hotword_reading_deferrals.json', deferred)
            continue
        atomic_write_json(workspace / f'hotword-batch-{number}.review.json', reviewed)
        extended = retain_native_extensions(extended, reviewed['selected'])
        chosen.extend(reviewed['selected'])
    terms = {row['term'] for row in chosen}
    if not terms:
        raise ValueError('All native hotword partitions were empty; no supported hotwords to deliver')
    final_packet = subset_packet(extended, [row for row in extended['candidates'] if row['term'] in terms])
    final_packet['first_pass_selected'] = chosen
    final_packet['original_quality_count_targets'] = {
        'minimum': packet.get('minimum_term_count'), 'target': packet.get('target_term_count')}
    final_packet['minimum_term_count'] = 1
    final_packet['target_term_count'] = min(target, len(terms))
    final_packet['batch_scope'] = 'Global second pass over native first-pass selections, with their exact original source windows.'
    result = call(final_packet, prompt_rules + '\n这是全表最终二次审核：跨组同义去重，核查每个词的独立指向和原文支持，'
                  '仅对first_pass_selected保留、删除、去重或必要补全，不开展新一轮扩词；数量不足如实保留缺口。'
                  '不得重复同一个term；必要补全须复制本包原文作为evidence_aliases，不改引文标点。'
                  '保留原议题编号，返回review_output_shape，真实完成后second_pass_completed=true。',
                  'hotword-global-review', 1)
    if result.get('second_pass_completed') is not True:
        raise ValueError('Native global hotword second pass was not completed')
    result['delivery_policy'] = packet.get('delivery_policy')
    result['batch_review_audit'] = {'candidate_count': len(packet['candidates']), 'batch_count': len(batches),
                                   'native_runs': records, 'first_pass_count': len(chosen),
                                   'deferred_candidate_batches': deferred,
                                   'source_witness_quarantines': quarantined}
    return result
