"""Unit transport tests are not evidence of real vendor-model completion."""
import copy
import json
from pathlib import Path
import sys
import time
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_cwh_inline_review as worker


def packet():
    return {'topic_titles': ['公共服务'], 'items': [
        {'record_id': f'row-{i}', 'title': '公共服务部署', 'content': f'第{i}篇完整原文。实施效果取决于资金。'}
        for i in range(5)]}


def install_transport(monkeypatch, calls, *, bad_call=None):
    def run(command, **kwargs):
        calls.append(command)
        payload = json.loads(kwargs['input_text'].split('\n只处理本批', 1)[0])
        source = payload['packet']['items']
        items = [{'record_id': r['record_id'], 'decision': 'include', 'topic_hits': [1],
                  'review_reason': '真实第三方条件分析', 'ai_report_category': '解读性报道',
                  'interpretive_range': [f'o{n}/2', f'o{n}/2'], 'interpretive_verified': True}
                 for n, r in enumerate(source, 1)]
        if bad_call == len(calls):
            items = items[:-1]
        kwargs['stdout'].write(json.dumps({'type': 'result', 'result': json.dumps(
            {'review_method': 'ai_semantic_review', 'items': items}, ensure_ascii=False)}, ensure_ascii=False))
        return 0
    monkeypatch.setattr(worker, 'run_scoped_command', run)


def test_every_row_once_exact_spans_and_completed_batches_reused(tmp_path, monkeypatch):
    source, calls = packet(), []
    original = copy.deepcopy(source)
    install_transport(monkeypatch, calls)
    result = worker.review_overseas_batches(source, {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 100, batch_size=2)
    assert [r['record_id'] for r in result['items']] == [r['record_id'] for r in source['items']]
    assert len(calls) == 3 and source == original
    assert result['items'][2]['interpretive_range'] == ['o3/2', 'o3/2']
    assert result['items'][2]['interpretive_excerpt'] == '实施效果取决于资金。'
    assert result['items'][2]['reviewer_run_id'] == result['batch_review_audit']['actual_runs'][1]['session_id']
    second = worker.review_overseas_batches(source, {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 100, batch_size=2)
    assert len(calls) == 3 and all(r['cache_reused'] for r in second['batch_review_audit']['actual_runs'])


def test_failed_batch_preserves_previous_checkpoint_and_resumes_only_missing(tmp_path, monkeypatch):
    calls = []
    install_transport(monkeypatch, calls, bad_call=2)
    with pytest.raises(SystemExit) as error:
        worker.review_overseas_batches(packet(), {}, '', ['model', '{session_id}'], tmp_path,
            time.monotonic() + 100, batch_size=2)
    assert error.value.code == 65 and (tmp_path / 'overseas-batch-1/accepted_review.json').is_file()
    assert not (tmp_path / 'overseas-batch-2/accepted_review.json').exists()
    install_transport(monkeypatch, calls)
    result = worker.review_overseas_batches(packet(), {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 100, batch_size=2)
    assert len(calls) == 4 and len(result['items']) == 5
    assert result['batch_review_audit']['actual_runs'][0]['cache_reused']


def test_corrupted_cached_output_is_not_trusted(tmp_path, monkeypatch):
    calls = []
    install_transport(monkeypatch, calls)
    worker.review_overseas_batches(packet(), {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 100, batch_size=2)
    path = tmp_path / 'overseas-batch-2/accepted_review.json'
    path.write_text('{}', encoding='utf-8')
    worker.review_overseas_batches(packet(), {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 100, batch_size=2)
    assert len(calls) == 4


def test_no_budget_never_calls_vendor(tmp_path, monkeypatch):
    calls = []
    install_transport(monkeypatch, calls)
    with pytest.raises(SystemExit) as error:
        worker.review_overseas_batches(packet(), {}, '', ['model'], tmp_path, time.monotonic() + 5)
    assert error.value.code == 124 and not calls


@pytest.mark.parametrize('kind', ['public_top', 'overseas'])
def test_batch_tail_never_gives_public_top_foreign_summary_instructions(tmp_path, monkeypatch, kind):
    calls, prompts = [], []
    install_transport(monkeypatch, calls)
    transport = worker.run_scoped_command

    def capture(command, **kwargs):
        prompts.append(kwargs['input_text'])
        return transport(command, **kwargs)

    monkeypatch.setattr(worker, 'run_scoped_command', capture)
    worker.review_overseas_batches(packet(), {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 100, kind=kind)
    assert len(prompts) == 1
    assert ('summary_cn_simplified' in prompts[0]) is (kind == 'overseas')
    if kind == 'overseas':
        assert '实质判断' in prompts[0] and '必要依据与条件' in prompts[0]


def test_public_top_expansion_reuses_unchanged_complete_batches(tmp_path, monkeypatch):
    calls = []
    install_transport(monkeypatch, calls)
    source = packet()
    first = worker.review_overseas_batches(source, {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 100, batch_size=2, kind='public_top')
    source['items'].append({'record_id': 'row-5', 'content': 'Original added candidate'})
    second = worker.review_overseas_batches(source, {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 100, batch_size=2, kind='public_top')
    assert len(calls) == 4 and len(second['items']) == 6
    assert all(run['cache_reused'] for run in second['batch_review_audit']['actual_runs'][:2])
    assert first['items'][0]['reviewer_run_id'] == second['items'][0]['reviewer_run_id']
    assert (tmp_path / 'public_top_batch_runs.json').is_file()
