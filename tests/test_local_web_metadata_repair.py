import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_cwh_compiled_worker as worker


def case():
    packet = {'topic': '公共服务', 'period': {'start': '2026-01-01', 'end': '2026-01-04'},
              'items': [{'id': 'w1', 'origin': 'web', 'url': 'https://example.com/article',
                         'content': '机构报道\n01月02日 10:00\n某专家提出了具体判断。'}]}
    decision = {'topic': packet['topic'], 'heading': '建议完善具体公共服务', 'clusters': [],
                'items': [{'id': 'w1', 'decision': 'eligible', 'source': '机构报道',
                           'published_at': '2026-01-02', 'date_quote': '01月02日 10:00',
                           'reason': '具有独立观点', 'claims': []}]}
    return packet, decision


def test_missing_full_date_gets_one_local_repair_without_inferred_year(monkeypatch, tmp_path):
    packet, decision = case()
    frozen = copy.deepcopy((packet, decision))
    calls = []
    def model(request, prompt, command, workspace, label, timeout, **kwargs):
        calls.append((request, timeout, kwargs))
        selected = request['topics'][0]['prior_selected']
        assert selected[0]['repairable_source_fields'] == ['date_quote', 'published_at']
        patch = copy.deepcopy(decision)
        patch['items'][0].update(decision='excluded', reason='无原文完整发布日期，留待补取', claims=[])
        return {'topics': [patch]}, {'session_id': 'actual-local-repair', 'seconds': 1}
    monkeypatch.setattr(worker, 'semantic_json', model)
    result, run = worker.repair_topic_web_metadata(packet, decision, [], tmp_path, 100, 'local')
    assert len(calls) == 1 and calls[0][1] == 45 and calls[0][2]['reuse_cache']
    assert result['items'][0]['decision'] == 'excluded'
    assert result['items'][0]['date_quote'] == decision['items'][0]['date_quote']
    assert (packet, decision) == frozen
    assert run['session_id'] == 'actual-local-repair'


def test_still_unanchored_date_cannot_pass_after_repair(monkeypatch, tmp_path):
    packet, decision = case()
    monkeypatch.setattr(worker, 'semantic_json', lambda *args, **kwargs:
                        ({'topics': [copy.deepcopy(decision)]}, {'session_id': 'not-passed'}))
    with pytest.raises(ValueError, match='Web publication date not anchored'):
        worker.repair_topic_web_metadata(packet, decision, [], tmp_path, 45, 'local')


def test_valid_metadata_adds_no_model_call_even_without_remaining_time(monkeypatch, tmp_path):
    packet, decision = case()
    packet['items'][0]['content'] = '机构报道\n发布日期：2026年1月2日\n真实观点'
    decision['items'][0]['date_quote'] = '2026年1月2日'
    monkeypatch.setattr(worker, 'semantic_json', lambda *args, **kwargs: pytest.fail('No repair needed'))
    result, run = worker.repair_topic_web_metadata(packet, decision, [], tmp_path, 0, 'local')
    assert result == decision and run is None


def test_invalid_metadata_cannot_borrow_time_after_deadline(monkeypatch, tmp_path):
    packet, decision = case()
    monkeypatch.setattr(worker, 'semantic_json', lambda *args, **kwargs: pytest.fail('No time extension'))
    with pytest.raises(TimeoutError, match='metadata repair budget'):
        worker.repair_topic_web_metadata(packet, decision, [], tmp_path, 14, 'local')
