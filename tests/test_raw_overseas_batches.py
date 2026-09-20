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


def install_transport(monkeypatch, calls, *, bad_call=None, bad_calls=()):
    def run(command, **kwargs):
        calls.append(command)
        payload = json.loads(kwargs['input_text'].split('\n只处理本批', 1)[0])
        source = payload['packet']['items']
        items = [{'record_id': r['record_id'], 'decision': 'include', 'topic_hits': [1],
                  'review_reason': '真实第三方条件分析', 'ai_report_category': '解读性报道',
                  'interpretive_range': [f'o{n}/2', f'o{n}/2'], 'interpretive_verified': True}
                 for n, r in enumerate(source, 1)]
        if bad_call == len(calls) or len(calls) in bad_calls:
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
    install_transport(monkeypatch, calls, bad_calls=(2, 3))
    with pytest.raises(SystemExit) as error:
        worker.review_overseas_batches(packet(), {}, '', ['model', '{session_id}'], tmp_path,
            time.monotonic() + 100, batch_size=2)
    assert error.value.code == 65 and (tmp_path / 'overseas-batch-1/accepted_review.json').is_file()
    assert not (tmp_path / 'overseas-batch-2/accepted_review.json').exists()
    install_transport(monkeypatch, calls)
    result = worker.review_overseas_batches(packet(), {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 100, batch_size=2)
    assert len(calls) == 5 and len(result['items']) == 5
    assert result['batch_review_audit']['actual_runs'][0]['cache_reused']


def test_invalid_batch_gets_one_fresh_bounded_review_not_guessed_ids(tmp_path, monkeypatch):
    source, calls, prompts, limits = packet(), [], [], []
    install_transport(monkeypatch, calls, bad_call=2)
    transport = worker.run_scoped_command

    def capture(command, **kwargs):
        prompts.append(kwargs['input_text'])
        limits.append(kwargs['timeout'])
        return transport(command, **kwargs)

    monkeypatch.setattr(worker, 'run_scoped_command', capture)
    result = worker.review_overseas_batches(source, {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 100, batch_size=2)
    assert len(calls) == 4
    repaired = result['batch_review_audit']['actual_runs'][1]
    assert repaired['session_id'] != repaired['original_rejected_run']['session_id']
    assert repaired['original_rejected_run']['exit_code'] == 0
    assert repaired['repair_reason'] == 'review must cover exactly every packet record_id once'
    assert limits[2] <= 45 and '上一次真实校验失败' in prompts[2]
    assert result['items'][2]['reviewer_run_id'] == repaired['session_id']
    assert result['items'][2]['interpretive_excerpt'] == source['items'][2]['content'].split('。')[1] + '。'
    again = worker.review_overseas_batches(source, {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 100, batch_size=2)
    assert len(calls) == 4 and again['batch_review_audit']['actual_runs'][1]['cache_reused']


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


def test_available_failed_batch_does_not_lose_later_native_results(tmp_path, monkeypatch):
    calls = []
    install_transport(monkeypatch, calls)
    native = worker.run_scoped_command
    attempts = []
    def interrupted(command, **kwargs):
        attempts.append(command)
        if len(attempts) == 1:
            return 124
        return native(command, **kwargs)
    monkeypatch.setattr(worker, 'run_scoped_command', interrupted)
    result = worker.review_overseas_batches(packet(), {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 300, batch_size=2, deliver_available=True)
    assert [r['record_id'] for r in result['items']] == ['row-2', 'row-3', 'row-4']
    assert result['items'][0]['interpretive_range'] == ['o3/2', 'o3/2']
    assert result['items'][0]['interpretive_excerpt'] == '实施效果取决于资金。'
    assert [r['record_id'] for r in result['deferred_records']] == ['row-0', 'row-1']
    assert all(r['actual_run']['exit_code'] == 124 for r in result['deferred_records'])
    assert result['review_complete'] is False


def test_available_exhausted_budget_is_not_native_review(tmp_path, monkeypatch):
    from cwh_semantic_recovery import valid_raw_deferrals
    calls = []
    install_transport(monkeypatch, calls)
    result = worker.review_overseas_batches(packet(), {}, '', ['model'], tmp_path,
        time.monotonic() - 1, deliver_available=True)
    assert not calls and not result['items']
    assert result['review_method'] == 'host_partial_review'
    assert valid_raw_deferrals(result, [r['record_id'] for r in packet()['items']], [])


def test_available_auth_failure_is_not_silently_hidden(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, 'run_scoped_command', lambda *a, **kw: 23)
    with pytest.raises(SystemExit) as error:
        worker.review_overseas_batches(packet(), {}, '', ['model'], tmp_path,
            time.monotonic() + 100, deliver_available=True)
    assert error.value.code == 23


@pytest.mark.parametrize('span', ['[o1/1, o1/2]', '["o1/1", "o1/2"]'])
def test_stringified_pair_changes_only_encoding_and_keeps_exact_source(span):
    source = packet()
    native = {'items': [{'record_id': 'row-0', 'decision': 'include', 'interpretive_range': span}]}
    frozen = copy.deepcopy((source, native))
    resolved = worker.resolve_overseas_spans(source, native)['items'][0]
    assert resolved['interpretive_range'] == ['o1/1', 'o1/2']
    assert resolved['interpretive_excerpt'] == source['items'][0]['content']
    assert resolved['transport_repairs'][0] == {'reason': 'lossless_stringified_segment_pair', 'original_interpretive_range': span}
    assert (source, native) == frozen


@pytest.mark.parametrize('span', ['[o1/2, o1/1]', '[o1/1, o2/2]', '[o1/1, o1/999]',
    '[o1/1, o1/2, o1/2]', '[1,2]', '[o1/1, o1/2] trailing'])
def test_stringified_range_never_guesses_ids_order_or_source(span):
    with pytest.raises(ValueError):
        worker.resolve_overseas_spans(packet(), {'items': [{'record_id': 'row-0', 'interpretive_range': span}]})


@pytest.mark.parametrize('decision,category', [('include', '事实性报道'), ('exclude', '解读性报道')])
def test_empty_placeholders_are_only_lossless_when_no_quote_is_asserted(decision, category):
    native = {'items': [{'record_id': 'row-0', 'decision': decision,
        'ai_report_category': category, 'interpretive_verified': False, 'interpretive_range': ['', '']}]}
    original = copy.deepcopy(native)
    row = worker.resolve_overseas_spans(packet(), native)['items'][0]
    assert row['interpretive_range'] == [] and 'interpretive_excerpt' not in row
    assert row['transport_repairs'][0]['reason'] == 'lossless_empty_segment_pair'
    assert native == original


@pytest.mark.parametrize('verified,category', [(True, '事实性报道'), (False, '解读性报道'), (None, '事实性报道')])
def test_empty_pair_never_creates_or_downgrades_interpretive_evidence(verified, category):
    with pytest.raises(ValueError):
        worker.resolve_overseas_spans(packet(), {'items': [{'record_id': 'row-0', 'decision': 'include',
            'ai_report_category': category, 'interpretive_verified': verified, 'interpretive_range': ['', '']}]})


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


def test_native_method_is_host_provenance_not_another_semantic_request(tmp_path, monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        payload = json.loads(kwargs['input_text'].split('\n只处理本批', 1)[0])
        items = [{'record_id': row['record_id'], 'decision': 'exclude', 'topic_hits': [],
                  'review_reason': 'Original article is unrelated'} for row in payload['packet']['items']]
        kwargs['stdout'].write(json.dumps({'type': 'result', 'result': json.dumps({'items': items})}))
        return 0
    monkeypatch.setattr(worker, 'run_scoped_command', run)
    result = worker.review_overseas_batches(packet(), {}, '', ['model', '{session_id}'], tmp_path,
        time.monotonic() + 100, kind='public_top')
    assert len(calls) == 1 and len(result['items']) == 5
    assert all(row['decision'] == 'exclude' for row in result['items'])
    saved = json.loads((tmp_path / 'public_top-batch-1/accepted_review.json').read_text('utf-8'))
    audit = saved['transport_repairs'][0]
    assert audit['kind'] == 'host_observed_native_review_method'
    assert audit['session_id'] == result['batch_review_audit']['actual_runs'][0]['session_id']


@pytest.mark.parametrize('method', [None, 'human_review', 'unknown'])
def test_explicit_wrong_method_is_not_overwritten(method):
    answer = {'review_method': method, 'items': []}
    frozen = copy.deepcopy(answer)
    assert worker.stamp_native_review_method(answer, {'exit_code': 0, 'session_id': 'native', 'log': 'original'}) == frozen
    with pytest.raises(ValueError, match='review_method'):
        worker.validate_transport_result('public_top', {'items': []}, answer)


def test_provenance_stamp_never_fills_missing_rows_or_without_native_success():
    answer = {'items': []}
    assert worker.stamp_native_review_method(answer, {'exit_code': 124}) == answer
    stamped = worker.stamp_native_review_method(answer, {'exit_code': 0, 'session_id': 'native', 'log': 'original'})
    assert answer == {'items': []}
    with pytest.raises(ValueError, match='exactly every'):
        worker.validate_transport_result('public_top', packet(), stamped)
