"""Agenda provenance/transport tests, without model calls or baseline answers."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from cwh_meeting_intake import snapshot, validate_review
from cwh_meeting_lead import report_agenda_fields
from cwh_writing_rules import opening_paragraph


def context_fixture():
    text = ('国务院总理李强8月9日主持召开国务院常务会议\n'
            '听取网络建设情况汇报\n研究公共服务有关工作\n'
            '会议听取网络建设情况汇报。会议研究公共服务有关工作。')
    source = snapshot({'content': text, 'published_at': '2027-08-09'}, 'test_fixture')
    review = {'source_sha256': source['source_sha256'], 'meeting_date': '2027-08-09',
              'meeting_date_quote': '李强8月9日主持召开国务院常务会议',
              'full_text_read': True, 'complete_communique': True,
              'meeting_summary': '会议听取网络建设情况汇报，研究公共服务有关工作。',
              'topics': [{'title': '网络建设', 'aliases': ['网络'], 'source_excerpt': '会议听取网络建设情况汇报。'},
                         {'title': '公共服务', 'aliases': ['公共服务'], 'source_excerpt': '会议研究公共服务有关工作。'}]}
    return validate_review({'sources': [source], 'expected_date': '2027-08-09'}, review)


def write_context(tmp_path, context):
    path = tmp_path / 'meeting_context.json'
    path.write_text(json.dumps(context, ensure_ascii=False), encoding='utf-8')
    return path


@pytest.mark.parametrize('prefix', ['会议', '李强8月9日主持召开国务院常务会议，',
                                     '国务院总理李强8月9日主持召开国务院常务会议，', ''])
def test_current_agenda_preserves_each_action_without_repeating_chair(tmp_path, prefix):
    context = context_fixture()
    context['review']['meeting_summary'] = prefix + '听取网络建设情况汇报，研究公共服务有关工作。'
    path = write_context(tmp_path, context)
    fields, audit = report_agenda_fields(path, '2027-08-09国务院常务会议', ['网络建设', '公共服务'])
    assert audit['status'] == 'source_mapped'
    assert audit['model_call_added'] is False
    paragraph = opening_paragraph(fields, '8月9日', '不应使用这段简短标签')
    assert paragraph.count('主持召开') == 1
    assert '听取网络建设情况汇报，研究公共服务有关工作。' in paragraph
    assert fields['agenda_source_sha256'] == context['source']['source_sha256']
    assert json.loads(path.read_text('utf-8')) == context


@pytest.mark.parametrize('action', ['对公共服务工作作出进一步部署', '进一步部署公共服务工作'])
def test_literal_action_lead_is_not_downgraded_to_an_agenda_label_list(tmp_path, action):
    text = '国务院总理李强8月9日主持召开国务院常务会议，' + action + '。'
    source = snapshot({'content': text, 'published_at': '2027-08-09'}, 'test_fixture')
    review = {'source_sha256': source['source_sha256'], 'meeting_date': '2027-08-09',
              'meeting_date_quote': '李强8月9日主持召开国务院常务会议',
              'full_text_read': True, 'complete_communique': True, 'meeting_summary': action + '。',
              'topics': [{'title': '公共服务', 'aliases': ['公共服务'], 'source_excerpt': text}]}
    context = validate_review({'sources': [source], 'expected_date': '2027-08-09'}, review)
    fields, audit = report_agenda_fields(write_context(tmp_path, context), '2027-08-09', ['公共服务'])
    assert audit['status'] == 'source_mapped'
    rendered = opening_paragraph(fields, '8月9日', '公共服务')
    assert action in rendered and '会议涉及' not in rendered


@pytest.mark.parametrize('mutation', ['source', 'date', 'unreviewed', 'invented', 'missing_topic', 'topics'])
def test_bad_or_partial_agenda_is_audited_without_blocking_other_output(tmp_path, mutation):
    context = copy.deepcopy(context_fixture())
    topics = ['网络建设', '公共服务']
    if mutation == 'source':
        context['source']['source_text'] += '篡改'
    elif mutation == 'date':
        context['review']['meeting_date'] = '2027-08-10'
    elif mutation == 'unreviewed':
        context['status'] = 'waiting_ai'
    elif mutation == 'invented':
        context['review']['meeting_summary'] = '决定取消网络建设，部署削减公共服务。'
    elif mutation == 'missing_topic':
        context['review']['meeting_summary'] = '听取网络建设情况汇报。'
    elif mutation == 'topics':
        topics.reverse()
    fields, audit = report_agenda_fields(write_context(tmp_path, context), '2027-08-09', topics)
    assert fields == {}
    assert audit['status'] == 'retained_topic_fallback'
    assert audit['reason']


def test_missing_context_and_broken_file_are_optional(tmp_path):
    assert report_agenda_fields('', '2027-08-09', [])[1]['status'] == 'not_provided'
    path = tmp_path / 'invalid.json'
    path.write_text('{', encoding='utf-8')
    assert report_agenda_fields(path, '2027-08-09', [])[1]['status'] == 'retained_topic_fallback'


def test_verified_headline_survives_only_summary_mapping_failure(tmp_path):
    context = context_fixture()
    context['source']['title'] = '李强主持召开国务院常务会议 听取网络建设情况汇报等'
    context['review']['meeting_summary'] = '研究公共服务有关工作，听取网络建设情况汇报。'
    fields, audit = report_agenda_fields(write_context(tmp_path, context), '2027-08-09', ['网络建设', '公共服务'])
    assert fields['focus_title'] == context['source']['title']
    assert 'agenda_text' not in fields and audit['verified_focus_retained'] is True
    context['source']['source_text'] += '篡改原文'
    fields, audit = report_agenda_fields(write_context(tmp_path, context), '2027-08-09', ['网络建设', '公共服务'])
    assert fields == {} and audit['verified_focus_retained'] is False


def test_render_command_hands_off_only_this_jobs_context(tmp_path):
    from run_cwh_resumable_pipeline import CwhPipeline, build_specs
    pipeline = CwhPipeline(tmp_path / 'job', {'agenda': '2027-08-09', 'execution_profile': 'bounded_60m'})
    path = write_context(pipeline.artifacts, context_fixture())
    runner = Mock()
    runner.run_command.return_value = (0, tmp_path / 'test.log')
    spec = next(s for s in build_specs() if s.stage_id == 'render')
    pipeline.render(runner, spec)  # No actual render, intentionally no output files.
    command = runner.run_command.call_args.args[1]
    assert command[command.index('--meeting-context') + 1] == str(path)
