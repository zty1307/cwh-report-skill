"""No paid model calls: deterministic intake contracts and failure injections."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import cwh_meeting_intake as intake


def fixture():
    body = '国务院总理李强7月31日主持召开国务院常务会议。会议研究电网和物流网建设。会议审议基金条例。'
    source = intake.snapshot({'content': body, 'published_at': '2026-07-31'}, 'raw_public_article')
    review = {'source_sha256': source['source_sha256'], 'meeting_date': '2026-07-31',
              'meeting_date_quote': '李强7月31日主持召开国务院常务会议',
              'full_text_read': True, 'complete_communique': True, 'meeting_summary': '研究网络建设，审议基金条例。',
              'topics': [{'title': '电网和物流网建设', 'aliases': ['电网', '物流网'], 'source_excerpt': '会议研究电网和物流网建设。'},
                         {'title': '基金条例', 'aliases': ['基金'], 'source_excerpt': '会议审议基金条例。'}]}
    packet = {'expected_date': '2026-07-31', 'sources': [source]}
    return packet, review


@pytest.mark.parametrize('url', ['http://127.0.0.1/', 'https://gov.cn.evil.test/', 'https://ydata.woa.com/', 'file:///etc/passwd', 'https://user:pw@www.gov.cn/'])
def test_reject_unapproved_url(url):
    assert not intake.is_gov_url(url)


def test_full_text_hash_date_and_literal_topic_checks():
    packet, review = fixture()
    assert intake.validate_review(packet, review)['status'] == 'reviewed'
    for change in ({'full_text_read': False}, {'complete_communique': False}, {'source_sha256': 'old'},
                   {'meeting_date': '2026-08-01'}, {'meeting_date_quote': '7月30日'}, {'topics': []}):
        with pytest.raises(ValueError):
            intake.validate_review(packet, {**review, **change})
    altered = copy.deepcopy(packet)
    altered['sources'][0]['source_text'] += '篡改'
    with pytest.raises(ValueError, match='哈希'):
        intake.validate_review(altered, review)


def test_same_month_day_previous_year_is_rejected():
    packet, review = fixture()
    packet['sources'][0]['published_at'] = '2025-07-31'
    with pytest.raises(ValueError, match='年份'):
        intake.validate_review(packet, review)


def test_reversed_agenda_quotes_are_not_confirmed_order():
    packet, review = fixture()
    review['topics'].reverse()
    with pytest.raises(ValueError, match='顺序'):
        intake.validate_review(packet, review)


@pytest.mark.parametrize('source,account', [('中国政府网', ''), ('公众号', '中国政府网')])
def test_raw_reader_scans_beyond_top_ten_and_stale_dimension(tmp_path, source, account):
    from unittest.mock import MagicMock
    (tmp_path / 'articles.xlsx').touch()
    sheet = MagicMock()
    sheet.title = '最热公号文章'
    sheet.calculate_dimension.return_value = 'A1'
    sheet.iter_rows.return_value = iter([
        ('来源', '标题', '正文', '链接', '发布时间', '昵称'),
        *[('其他媒体', '文章', '全文', '', '2026-07-31', '')] * 68,
        (source, '今日国务院常务会', '7月31日召开国务院常务会议。完整正文。', '', '2026-07-31', account)])
    book = MagicMock()
    book.sheetnames = ['最热公号文章']
    book.__getitem__.return_value = sheet
    with patch('openpyxl.load_workbook', return_value=book):
        sources, audit = intake.discover_raw(tmp_path)
    sheet.reset_dimensions.assert_called_once()
    assert sources[0]['source_row'] == 70
    assert sources[0]['publisher'] == '中国政府网'
    assert audit['rows_scanned'] == 69
    assert audit['top_limit_applied'] is False
    book.close.assert_called_once()


def test_raw_full_text_precedes_url_and_is_never_truncated(tmp_path):
    packet, _ = fixture()
    source = packet['sources'][0]
    source['source_text'] += '全文保留' * 10000
    source['source_sha256'] = intake.digest(source['source_text'])
    with patch.object(intake, 'discover_raw', return_value=([source], {'rows_scanned': 2000})), patch.object(intake, 'read_public_page') as fetch:
        result, state = intake.prepare(tmp_path, '2026-07-31', tmp_path, 'https://www.gov.cn/example.htm')
    fetch.assert_not_called()
    assert result['sources'][0]['source_text'] == source['source_text']
    assert state['ai_status'] == 'not_reviewed'
    assert result['discovery_audit']['rows_scanned'] == 2000


def test_fallback_missing_host_is_not_ai_success(tmp_path):
    with patch.object(intake, 'read_public_page', return_value={'status': 'completed', 'source_text': fixture()[0]['sources'][0]['source_text'], 'final_url': 'https://www.gov.cn/a', 'url': 'https://www.gov.cn/a'}):
        packet, state = intake.prepare('', '2026-07-31', tmp_path, 'https://www.gov.cn/a')
    with patch.dict('os.environ', {'CWH_SEMANTIC_COMMAND_JSON': ''}):
        assert intake.review_packet(packet, tmp_path) is None
    assert state['status'] == 'waiting_ai'
    assert not (tmp_path / 'meeting_context.json').exists()


def test_order_confirmation_count_and_named_file_mapping(tmp_path):
    packet, review = fixture()
    context = intake.validate_review(packet, review)
    paths = [tmp_path / '总.xlsx', tmp_path / '子1.xlsx', tmp_path / '基金.xlsx']
    for p in paths:
        p.touch()  # discovery fixture; no workbook authoring
    def profile(path, config):
        return {'path': path, 'file': path.name, 'structural_roles': ['heat']}
    with patch('raw_system_workbook_pipeline.profile_raw_workbook', side_effect=profile):
        with pytest.raises(ValueError, match='明确确认'):
            intake.metadata_from_context(context, tmp_path)
        metadata = intake.metadata_from_context(context, tmp_path, True)
        assert metadata['child_file_indices'] == {'子1.xlsx': 1, '基金.xlsx': 2}
        assert len(metadata['topic_titles']) == 2  # do not split the combined first topic
        paths[2].unlink()
        with pytest.raises(ValueError, match='数量不一致'):
            intake.metadata_from_context(context, tmp_path, True)


def test_no_old_date_default():
    with pytest.raises(ValueError, match='含年份'):
        intake.expected_date('7月31日国务院常务会议')


def test_pipeline_emits_model_neutral_task_before_workbook(tmp_path):
    from run_cwh_resumable_pipeline import CwhPipeline, build_specs
    contract = {'agenda': '2026-07-31', 'raw_input_dir': str(tmp_path), 'execution_profile': 'bounded_60m'}
    pipeline = CwhPipeline(tmp_path / 'job', contract)
    packet, _ = fixture()
    with patch.object(intake, 'prepare', return_value=(packet, {'status': 'waiting_ai'})):
        outcome = pipeline.workbook(pipeline.runner, next(s for s in build_specs() if s.stage_id == 'workbook'))
    assert outcome.status == 'waiting_ai'
    task = json.loads((pipeline.tasks / 'workbook.json').read_text('utf-8'))
    assert task['task_type'] == 'meeting_communique_review'
    assert '通稿' in task['rules'][0]
    assert not (pipeline.artifacts / 'CWH舆情情况_标准总表.xlsx').exists()


def test_downstream_task_keeps_full_context_and_rejects_other_period(tmp_path):
    from run_cwh_resumable_pipeline import CwhPipeline, ai_task
    contract = {'agenda': '2026-07-31', 'raw_input_dir': str(tmp_path), 'execution_profile': 'bounded_60m'}
    pipeline = CwhPipeline(tmp_path / 'job', contract)
    packet, review = fixture()
    intake.atomic_write_json(pipeline.artifacts / 'meeting_context.json', intake.validate_review(packet, review))
    path = ai_task(pipeline.runner, 'domestic_viewpoints', task_type='test', expected_output=pipeline.artifacts / 'analysis.json', inputs={}, rules=[])
    task = json.loads(path.read_text('utf-8'))
    assert task['inputs']['meeting_context']['source']['source_text'] == packet['sources'][0]['source_text']
    pipeline.runner.input_contract['agenda'] = '2026-08-01'
    with pytest.raises(ValueError, match='日期'):
        ai_task(pipeline.runner, 'domestic_viewpoints', task_type='test', expected_output=tmp_path / 'out.json', inputs={}, rules=[])


def test_supplement_url_remains_available_after_raw_candidate_is_incomplete(tmp_path):
    packet, _ = fixture()
    with patch.object(intake, 'discover_raw', return_value=(packet['sources'], {})), patch.object(intake, 'read_public_page', return_value={
            'status': 'completed', 'source_text': '2026-07-31\n' + packet['sources'][0]['source_text'],
            'url': 'https://www.gov.cn/a', 'final_url': 'https://www.gov.cn/a'}):
        result, _ = intake.prepare(tmp_path, '2026-07-31', tmp_path, 'https://www.gov.cn/a', supplement_url=True)
    assert {s['origin'] for s in result['sources']} == {'raw_public_article', 'manual_public_url'}


def test_rejected_review_is_not_reused_as_success(tmp_path):
    packet, review = fixture()
    rejected = {**review, 'full_text_read': False}
    run = {'session_id': 'unit-test-only', 'exit_code': 0}
    with patch.dict('os.environ', {'CWH_SEMANTIC_COMMAND_JSON': '["unit-test-only"]'}), patch('cwh_host_research.semantic_json', side_effect=[(rejected, run), (review, run)]) as model:
        context = intake.review_packet(packet, tmp_path)
    assert model.call_args_list[1].kwargs['reuse_cache'] is False
    assert context['model_run']['session_id'] == 'unit-test-only'
    assert len(list(tmp_path.glob('review_*.json'))) == 2
    assert json.loads((tmp_path / 'communique_status.json').read_text('utf-8'))['ai_status'] == 'reviewed'


def test_repair_is_bounded_and_never_weakens_literal_mapping(tmp_path):
    packet, review = fixture()
    review['topics'][0]['aliases'] = ['原文不存在的政策']
    with patch.dict('os.environ', {'CWH_SEMANTIC_COMMAND_JSON': '["test"]'}), patch('cwh_host_research.semantic_json', return_value=(review, {})) as model:
        with pytest.raises(ValueError, match='别名'):
            intake.review_packet(packet, tmp_path)
    assert model.call_count == 2
    assert not (tmp_path / 'meeting_context.json').exists()


def test_timeout_retries_but_quota_does_not(tmp_path):
    from cwh_host_research import HostModelError
    packet, review = fixture()
    with patch.dict('os.environ', {'CWH_SEMANTIC_COMMAND_JSON': '["test"]'}), patch('cwh_host_research.semantic_json', side_effect=[HostModelError('timeout', 124), (review, {})]) as model:
        assert intake.review_packet(packet, tmp_path)['status'] == 'reviewed'
    assert model.call_count == 2
    assert model.call_args.args[-1] <= 240
    with patch.dict('os.environ', {'CWH_SEMANTIC_COMMAND_JSON': '["test"]'}), patch('cwh_host_research.semantic_json', side_effect=HostModelError('quota', 23)) as model:
        with pytest.raises(HostModelError):
            intake.review_packet(packet, tmp_path)
    assert model.call_count == 1


def test_intake_repairs_share_one_capped_clock(tmp_path):
    from cwh_host_research import HostModelError
    packet, review = fixture()
    with patch.dict('os.environ', {'CWH_SEMANTIC_COMMAND_JSON': '["test"]'}), patch.object(intake.time, 'monotonic', side_effect=[0, 0, 100]), patch('cwh_host_research.semantic_json', side_effect=[HostModelError('early timeout', 124), (review, {})]) as model:
        assert intake.review_packet(packet, tmp_path, timeout=600)['status'] == 'reviewed'
    assert [call.args[-1] for call in model.call_args_list] == [240, 140]
    with patch.dict('os.environ', {'CWH_SEMANTIC_COMMAND_JSON': '["test"]'}), patch.object(intake.time, 'monotonic', side_effect=[0, 0, 240]), patch('cwh_host_research.semantic_json', side_effect=HostModelError('timeout', 124)) as model:
        with pytest.raises(TimeoutError):
            intake.review_packet(packet, tmp_path, timeout=240)
    assert model.call_count == 1


def test_numbered_full_text_materialization_has_no_truncation():
    packet, legacy = fixture()
    source = packet['sources'][0]
    source['source_text'] = '国务院总理李强7月31日主持召开国务院常务会议。\n会议研究电网和物流网建设。\n会议审议基金条例。'
    source['source_sha256'] = intake.digest(source['source_text'])
    wire = intake.compact_packet(packet)
    assert ''.join(p['text'] for p in wire['sources'][0]['paragraphs']) == source['source_text']
    native = {k: v for k, v in legacy.items() if k not in {'source_sha256', 'meeting_date_quote', 'topics'}}
    native.update(source_id='s1', date_anchor='p1', topics=[
        {'title': '电网和物流网建设', 'aliases': ['电网'], 'anchor_ids': ['p2']},
        {'title': '基金条例', 'aliases': ['基金'], 'anchor_ids': ['p3']}])
    review = intake.materialize_review(packet, native)
    assert intake.validate_review(packet, review)['status'] == 'reviewed'
    assert review['source_sha256'] == source['source_sha256']
    assert review['topics'][0]['source_excerpt'] == '会议研究电网和物流网建设。'
    assert 'source_excerpt' not in native['topics'][0]
    for broken in ({'source_id': 's99'}, {'date_anchor': 'p99'}):
        with pytest.raises(ValueError):
            intake.materialize_review(packet, {**native, **broken})
    for anchors in (['p2', 'p1'], ['p1', 'p3'], ['p2', 'p2'], ['p99']):
        altered = copy.deepcopy(native)
        altered['topics'][0]['anchor_ids'] = anchors
        with pytest.raises(ValueError):
            intake.materialize_review(packet, altered)


@pytest.mark.parametrize('body', ['首句。次句！尾句？', '标题\r\n正文。\r\n\r\n第二段。尾部无句号', '含“引文。”后续内容\n', '无换行' * 20000], ids=['sentences', 'crlf', 'quotes', 'long-line'])
def test_numbered_source_preserves_all_characters(body):
    assert ''.join(intake.source_parts(body)) == body


def test_numbered_single_line_export_keeps_separate_agenda_anchors():
    packet, _ = fixture()
    parts = intake.compact_packet(packet)['sources'][0]['paragraphs']
    assert len(parts) == 3
    assert parts[1]['text'] == '会议研究电网和物流网建设。'


def test_only_unique_book_bracket_variants_can_be_mapped():
    source = '审议《修改〈甲类许可办法〉的决定》，办理许可。'
    assert intake.literal_book_brackets('修改《甲类许可办法》的决定', source) == '修改〈甲类许可办法〉的决定'
    assert intake.literal_book_brackets('修改《乙类许可办法》的决定', source) == '修改《乙类许可办法》的决定'
    assert intake.literal_book_brackets('许可 办理', source) == '许可 办理'
    assert intake.literal_book_brackets('《甲》', '〈甲》及《甲〉') == '《甲》'
    assert intake.literal_book_brackets(None, source) is None


def test_repair_receives_all_topic_errors_in_one_pass():
    packet, review = fixture()
    review['topics'][0]['source_excerpt'] = '国务院总理李强7月31日主持召开国务院常务会议。'
    review['topics'][1]['aliases'] = ['不存在的法规']
    with pytest.raises(ValueError) as result:
        intake.validate_review(packet, review)
    assert '电网和物流网建设' in str(result.value)
    assert '不存在的法规' in str(result.value)
