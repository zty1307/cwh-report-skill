import copy
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_author_cache import cache_key, read_completed, save_completed
import run_cwh_compiled_worker as worker


def test_cache_preserves_actual_run_and_repairs_without_counting_it_as_new_work(tmp_path):
    path = tmp_path / 'completed.json'
    result = {'items': [{'id': 'r1', 'decision': 'excluded', 'reason': '真实原生判断', 'claims': []}],
              'transport_repairs': [{'actual_run': 'original-repair'}]}
    run = {'session_id': 'original-model-session', 'seconds': 31.5}
    before = copy.deepcopy((result, run))
    save_completed(path, 'key', result, run)
    cached, reused = read_completed(path, 'key')
    assert cached == result and reused['session_id'] == run['session_id']
    assert reused['cache_reused'] and reused['seconds'] == 0 and reused['original_execution_seconds'] == 31.5
    assert (result, run) == before


def test_changed_source_prompt_model_rules_or_result_invalidates_cache(tmp_path):
    path = tmp_path / 'completed.json'
    base = cache_key({'content': '原文'}, '提示', ['模型'], '规则')
    for values in [({'content': '改文'}, '提示', ['模型'], '规则'),
                   ({'content': '原文'}, '修复反馈', ['模型'], '规则'),
                   ({'content': '原文'}, '提示', ['另一模型'], '规则'),
                   ({'content': '原文'}, '提示', ['模型'], '新规则')]:
        assert cache_key(*values) != base
    save_completed(path, base, {'items': []}, {'session_id': 'actual'})
    assert read_completed(path, 'other') is None
    record = json.loads(path.read_text('utf-8'))
    record['payload']['result']['items'].append({'invented': True})
    path.write_text(json.dumps(record), encoding='utf-8')
    assert read_completed(path, base) is None


def test_author_resume_reuses_completed_local_repair_but_feedback_invalidates(monkeypatch, tmp_path):
    source = {'topic': '公共服务', 'items': [
        {'id': 'r1', 'origin': 'raw_monitoring', 'content': '完整原文，包含实际政策对象。'}]}
    calls = []
    def native(*args, **kwargs):
        calls.append('author')
        return {'items': [{'id': 'r1', 'decision': 'excluded', 'reason': '', 'claims': []}],
                'heading': '', 'clusters': []}, {'session_id': 'real-author-id', 'seconds': 2}
    def repair(packet, result, *args, **kwargs):
        calls.append('repair')
        result = copy.deepcopy(result)
        result['items'][0]['reason'] = '原生补充：只有政策事实，无新增判断'
        return result, {'session_id': 'real-repair-id', 'seconds': 1}
    monkeypatch.setattr(worker, 'semantic_json', native)
    monkeypatch.setattr(worker, 'repair_missing_reasons', repair)
    first, runs = worker.author_topic_decisions([source], '规则', [], tmp_path,
        time.monotonic() + 60, reuse_cache=True)
    second, reused = worker.author_topic_decisions([source], '规则', [], tmp_path,
        time.monotonic() + 60, reuse_cache=True)
    assert first == second and calls == ['author', 'repair']
    assert reused['topic_runs'][0]['missing_reason_completion_run'] == runs['topic_runs'][0]['missing_reason_completion_run']
    assert reused['topic_runs'][0]['cache_reused']
    worker.author_topic_decisions([source], '规则', [], tmp_path,
        time.monotonic() + 60, reuse_cache=True, feedback=['[公共服务]补充检查'])
    assert calls == ['author', 'repair', 'author', 'repair']
