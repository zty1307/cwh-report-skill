"""Failed HTTP slots may be replaced; originals and eligibility remain untouched."""
import copy
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_cwh_compiled_worker as worker


def fixture_rows():
    urls = ['https://example.test/a', 'https://example.test/b']
    pages = [{'url': urls[0], 'status': 'access_failed', 'blocker': '403'},
             {'url': urls[1], 'status': 'completed', 'source_text': '完整原文'}]
    observations = {'queries': [{'results': [{'url': url} for url in
        [*urls, 'https://example.test/c', 'https://example.test/d']]}]}
    return urls, pages, observations


def test_one_failed_slot_replaced_preserving_originals_and_cache(tmp_path, monkeypatch):
    urls, pages, observations = fixture_rows()
    originals = copy.deepcopy((urls, pages, observations))
    calls = []
    def fetch(workspace, selected, timeout):
        calls.append((workspace, selected, timeout))
        return [{'url': selected[0], 'status': 'completed', 'source_text': '补充完整原文'}]
    monkeypatch.setattr(worker, 'cached_public_pages', fetch)
    result = worker.recover_failed_page_slots(tmp_path, observations, urls, pages,
        {'execution_budget': {'max_full_page_fetches_per_topic': 4}}, time.monotonic() + 100)
    assert (urls, pages, observations) == originals
    assert result[:2] == pages and len(result) == 3
    assert calls == [(tmp_path / 'failed_page_recovery', ['https://example.test/c'], 8)]
    assert not any('decision' in row for row in result)
    audit = json.loads((tmp_path / 'failed_page_recovery/reading_audit.json').read_text('utf-8'))
    assert audit['attempted_total'] == 3 and audit['waves'] == 1


def test_full_reads_do_not_expand_or_treat_short_page_as_semantic_failure(tmp_path, monkeypatch):
    urls, pages, observations = fixture_rows()
    pages[0] = {'url': urls[0], 'status': 'completed', 'source_text': '短文但不是访问失败'}
    monkeypatch.setattr(worker, 'cached_public_pages', lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    assert worker.recover_failed_page_slots(tmp_path, observations, urls, pages,
        {'execution_budget': {'max_full_page_fetches_per_topic': 4}}, time.monotonic() + 100) is pages


def test_ceiling_legacy_plan_and_budget_never_trigger_extra_read(tmp_path, monkeypatch):
    urls, pages, observations = fixture_rows()
    monkeypatch.setattr(worker, 'cached_public_pages', lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    for plan, seconds in [({}, 100), ({'execution_budget': {'max_full_page_fetches_per_topic': 2}}, 100),
                          ({'execution_budget': {'max_full_page_fetches_per_topic': 4}}, 60)]:
        assert worker.recover_failed_page_slots(tmp_path, observations, urls, pages,
            plan, time.monotonic() + seconds) is pages


def test_failed_replacement_does_not_recursively_retry(tmp_path, monkeypatch):
    urls, pages, observations = fixture_rows()
    calls = []
    def fetch(workspace, selected, timeout):
        calls.append(selected)
        return [{'url': selected[0], 'status': 'access_failed', 'blocker': '403'}]
    monkeypatch.setattr(worker, 'cached_public_pages', fetch)
    result = worker.recover_failed_page_slots(tmp_path, observations, urls, pages,
        {'execution_budget': {'max_full_page_fetches_per_topic': 4}}, time.monotonic() + 100)
    assert len(calls) == 1 and len(result) == 3 and result[-1]['status'] == 'access_failed'
