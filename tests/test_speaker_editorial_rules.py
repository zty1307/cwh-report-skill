import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from cwh_writing_rules import attribution_format_issues, editorial_eligibility_prompt
from normalize_cwh_analysis import normalize_analysis
from report_rules import domestic_viewpoint_quality_issues


def payload(row):
    return {'viewpoints': {'by_topic': [{'topic': '设施改造', 'heading': '建议完善设施管护机制',
        'clusters': [{'summary': '建议明确设施管护责任', 'evidence': [row]}]}]}}


def test_ordinary_person_and_self_reported_career_do_not_pass_media_section_gate():
    for row in [
        {'attribution_status': 'ordinary_person', 'speaker_name': '张甲'},
        {'attribution_status': 'named_person', 'speaker_name': '张甲',
         'speaker_role': '陆续在制造业从事安全工作共17年'},
        {'attribution_status': 'named_person', 'speaker_name': '张甲'},
    ]:
        row['formal_claim'] = '建议落实设施管护责任，及时处理日常运行发现的风险。'
        issues = domestic_viewpoint_quality_issues(payload(row))
        assert any(i['code'] in {'ineligible_person_viewpoint', 'unverified_professional_identity'} for i in issues)


def test_professional_identity_is_not_confused_with_carrier_interview_metadata():
    row = {'attribution_status': 'named_person', 'speaker_name': '李甲',
           'speaker_role': '某研究院研究员', 'attribution': '某研究院研究员李甲',
           'source_excerpt': '某研究院研究员李甲在接受某报记者采访时表示，应明确管护责任。',
           'formal_claim': '应明确管护责任。'}
    assert not attribution_format_issues(row)
    row['formal_claim'] = '在接受某报记者采访时表示，应明确管护责任。'
    assert any(i[0] == 'interview_process_in_claim' for i in attribution_format_issues(row))
    row['formal_claim'] = '对某报记者表示，应明确管护责任。'
    assert any(i[0] == 'interview_process_in_claim' for i in attribution_format_issues(row))


def test_redundant_account_header_is_removed_before_freeze_with_original_preserved():
    for prefix in ['水利观察：', '水利观察称，', '微信公众号“水利观察”称，']:
        claim = prefix + '应明确管护责任，水利观察还建议公开维护预算。'
        row = {'attribution_status': 'self_media', 'speaker_name': '水利观察',
               'url': 'https://mp.weixin.qq.com/s/test', 'formal_claim': claim,
               'source_excerpt': claim}
        assert any(i[0] == 'repeated_account_attribution' for i in attribution_format_issues(row))
        data = normalize_analysis(payload(row))
        assert row['formal_claim'] == '应明确管护责任，水利观察还建议公开维护预算。'
        assert row['source_excerpt'] == claim and row['author_formal_claim'] == claim
        assert data['viewpoints']['by_topic'][0]['clusters'][0]['details'].startswith('微信公众号“水利观察”称，应明确')
        assert not attribution_format_issues(row)
        assert normalize_analysis(copy.deepcopy(data)) == data


def test_account_name_as_real_subject_is_not_removed():
    row = {'attribution_status': 'self_media', 'speaker_name': '水利观察',
           'formal_claim': '公开预算有助于监督，水利观察的分析也须接受核查。'}
    normalize_analysis(payload(row))
    assert row['formal_claim'] == '公开预算有助于监督，水利观察的分析也须接受核查。'


def test_media_rules_do_not_remove_real_comments():
    comment = {'author': '普通网友', 'content': '希望及时公开维护预算。'}
    data = {'viewpoints': {'by_topic': []}, 'comments': {'selected': [comment]}}
    assert normalize_analysis(copy.deepcopy(data))['comments']['selected'] == [comment]


def test_author_repair_and_independent_review_receive_the_shared_rules():
    from cwh_semantic_compiler import AUTHOR_PROMPT
    from cwh_semantic_repairs import REPAIR_PROMPT
    from run_cwh_compiled_worker import REVIEW_PROMPT
    shared = editorial_eligibility_prompt()
    for prompt in (shared, AUTHOR_PROMPT, REPAIR_PROMPT, REVIEW_PROMPT):
        assert '普通个人、普通网友' in prompt
        assert '采访过程' in prompt
        assert 'formal_claim直接写观点' in prompt
