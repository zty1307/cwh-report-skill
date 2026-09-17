"""Fault injection proves recovery mechanics, not live model quality."""
import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_semantic_recovery import POLICY, deferred_hotwords, is_deferred_hotwords
from test_raw_system_workbook_pipeline import OverseasSemanticReviewTests
import raw_system_workbook_pipeline as raw


def failure():
    return {'kind': 'model_timeout', 'actual_run': {'session_id': 'failed-call', 'exit_code': 124}, 'reason': 'timeout'}


def test_partial_overseas_retains_original_counts_and_unread_rows():
    fixture = OverseasSemanticReviewTests()
    fixture.setUp()
    review = fixture.review()
    missing = review['items'].pop()
    review.update(delivery_policy=POLICY, deferred_records=[{'record_id': missing['record_id'], **failure()}])
    result = raw.filter_overseas(fixture.rows, fixture.config, fixture.metadata, review=review,
                                monitoring_dates=['2026-01-01', '2026-01-02'])
    assert result['status'] == 'ai_review_partial' and result['counts_reconciled'] is False
    assert len(result['selected']) == 1
    assert result['decisions'][-1]['decision'] == 'deferred'
    assert result['decisions'][-1]['ai_reviewed'] is False
    total = [{'date': '2026-01-01', 'overseas_news': 99, 'domestic_news': 17}]
    children = {1: copy.deepcopy(total)}
    frozen = copy.deepcopy((total, children))
    reconciled = raw.reconcile_overseas_daily_counts(total, children, result)
    assert (reconciled['total_daily'], reconciled['child_daily']) == frozen
    review['deferred_records'] = []
    with pytest.raises(raw.PipelineError):
        raw.filter_overseas(fixture.rows, fixture.config, fixture.metadata, review=review,
                            monitoring_dates=['2026-01-01'])


def test_host_partial_flag_never_approves_native_rows():
    fixture = OverseasSemanticReviewTests()
    fixture.setUp()
    review = fixture.review()
    review['review_method'] = 'host_partial_review'
    with pytest.raises(raw.PipelineError, match='宿主待审'):
        raw.filter_overseas(fixture.rows, fixture.config, fixture.metadata, review=review,
                            monitoring_dates=['2026-01-01'])


def test_deferred_hotwords_can_render_honest_absence_not_a_fake_cloud(tmp_path):
    from openpyxl import Workbook
    from raw_system_workbook_portable import write_wordcloud
    from run_cwh_resumable_pipeline import validate_hotword_audit
    from formalize_cwh_report import apply_hotword_audit, hotword_paragraph
    audit = deferred_hotwords(failure())
    assert is_deferred_hotwords(audit)
    path = tmp_path / 'audit.json'
    path.write_text(json.dumps(audit), encoding='utf-8')
    assert not validate_hotword_audit(path, ['示例议题'])
    data = {'hotwords': [{'word': '旧词不得混入'}]}
    apply_hotword_audit(data, path)
    assert not data['hotwords']
    assert data['audit']['acceptance']['ready_for_formal_delivery'] is False
    assert hotword_paragraph(data) == audit['notice']
    book = Workbook()
    write_wordcloud(book, {'hotwords': audit}, tmp_path / 'does-not-exist.png')
    assert not book['词云']._images
    assert book['词云']['C2'].value == audit['notice']


@pytest.mark.parametrize('change', [{'selected': [{'term': '伪造'}]}, {'second_pass_completed': True},
                                 {'interruption': {}}, {'delivery_policy': 'strict'}])
def test_deferred_hotword_record_cannot_become_a_completion(change):
    audit = deferred_hotwords(failure())
    audit.update(change)
    assert not is_deferred_hotwords(audit)
