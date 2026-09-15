from pathlib import Path
import sys
import time
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_cwh_compiled_worker as worker


def test_each_topic_has_its_own_small_request_and_run_ids(monkeypatch, tmp_path):
    calls = []
    def model(packet, prompt, command, workspace, label, timeout, reuse_cache):
        calls.append((packet, prompt))
        assert 'topics' not in packet and packet['topic'] in prompt
        return {'items': [{'id': 'r1', 'decision': 'excluded', 'claims': [], 'reason': '仅事实'}],
                'heading': packet['topic'], 'clusters': []}, {'session_id': label, 'seconds': 1}
    monkeypatch.setattr(worker, 'semantic_json', model)
    packets = [{'topic': topic, 'items': [{'id': 'r1', 'content': content}]} for topic, content in [('动态甲', '甲原文'), ('动态乙', '乙原文')]]
    decisions, run = worker.author_topic_decisions(packets, '规则', [], tmp_path, time.monotonic()+60, reuse_cache=True)
    assert [d['topic'] for d in decisions] == ['动态甲', '动态乙']
    assert len(calls) == 2 and len(run['topic_runs']) == 2
    assert '乙原文' not in str(calls[0]) and '甲原文' not in str(calls[1])


def test_single_topic_partial_or_cross_topic_result_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, 'semantic_json', lambda *a, **k: ({'items': []}, {'session_id': 'r'}))
    with pytest.raises(ValueError, match='every item'):
        worker.author_topic_decisions([{'topic': '动态甲', 'items': [{'id': 'r1', 'content': '原文'}]}], '规则', [], tmp_path, time.monotonic()+60, reuse_cache=False)


def test_scoped_feedback_keeps_other_topic_requests_and_prior_repairs_cacheable(monkeypatch, tmp_path):
    cache, actual = {}, []
    def model(packet, prompt, command, workspace, label, timeout, reuse_cache):
        key = (str(packet), prompt, label)
        if not reuse_cache or key not in cache:
            actual.append(packet['topic'])
            cache[key] = ({'items': [{'id': 'r1', 'decision': 'excluded', 'reason': '仅会议事实', 'claims': []}],
                           'heading': packet['topic'], 'clusters': []}, {'session_id': label})
        return cache[key]
    monkeypatch.setattr(worker, 'semantic_json', model)
    packets = [{'topic': topic, 'items': [{'id': 'r1', 'content': topic + '原文'}]}
               for topic in ('动态甲', '动态乙', '动态丙')]
    for feedback in ([], ['[动态乙] JSON格式错误'], ['[动态丙] JSON格式错误']):
        worker.author_topic_decisions(packets, '规则', [], tmp_path, time.monotonic()+60,
                                     reuse_cache=True, feedback=feedback)
    assert actual == ['动态甲', '动态乙', '动态丙', '动态乙', '动态丙']


def test_parse_error_names_the_affected_topic(monkeypatch, tmp_path):
    def model(*args, **kwargs):
        raise ValueError('model returned no parseable review JSON')
    monkeypatch.setattr(worker, 'semantic_json', model)
    with pytest.raises(ValueError, match=r'\[动态甲\].*no parseable'):
        worker.author_topic_decisions([{'topic': '动态甲', 'items': []}], '规则', [], tmp_path,
                                     time.monotonic()+60, reuse_cache=True)
