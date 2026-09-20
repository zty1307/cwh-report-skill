"""Current editorial contract; synthetic meetings, no benchmark fact lookup."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))

from cwh_meeting_lead import source_focus_fields
from cwh_writing_rules import editorial_template_prompt
from formalize_cwh_report import total_event_paragraphs, hotword_paragraph, overseas_media_body_paragraphs
from raw_system_workbook_pipeline import channel_display_labels, domestic_difference_patterns
from report_rules import approved_source_layout_issues


def test_focus_is_one_news_headline_not_an_agenda_list():
    data = {'meeting': {'topics': ['研究公共服务', '听取网络建设汇报']},
            'statistics': {'total_spread': 80}}
    assert '舆论关注' not in total_event_paragraphs(data)[0]
    source = {'title': '张甲主持召开国务院常务会议 研究公共服务等',
              'source_sha256': 'fixture', 'url': 'https://example.test/news'}
    fields = source_focus_fields(source, {})
    data['meeting'].update(fields)
    assert '舆论关注“张甲主持召开国务院常务会议 研究公共服务等”相关话题' in total_event_paragraphs(data)[0]


def test_short_news_title_uses_literal_first_agenda_not_chair_default():
    source = {'title': '张甲主持召开国务院常务会议', 'source_sha256': 'fixture',
              'source_text': '研究公共服务有关工作，听取网络建设情况汇报。'}
    review = {'topics': [{'title': '研究公共服务有关工作'}, {'title': '听取网络建设情况汇报'}]}
    fields = source_focus_fields(source, review)
    assert fields['focus_title'] == '张甲主持召开国务院常务会议 研究公共服务有关工作等'
    review['topics'][0]['title'] = '研究未出现的政策'
    assert source_focus_fields(source, review) == {}


def test_editorial_hotword_frame_preserves_actual_terms_and_stance():
    data = {'hotwords': [{'topic': '服务', 'word': w} for w in ['服务点', '开放时间', '人员配置', '经费保障']],
            'viewpoints': {'by_topic': [{'topic': '服务', 'clusters': [{'summary': '期待明确人员经费保障'}]}]}}
    original = copy.deepcopy(data)
    text = hotword_paragraph(data)
    assert text == '从热词分布来看，“服务点”“开放时间”“人员配置”“经费保障”等词位居前列，舆论期待明确人员经费保障。'
    assert data == original


def fixture(topics):
    return {'viewpoints': {'by_topic': [{'topic': topic, 'clusters': [
        {'summary': '建议改善实际服务', 'evidence': [{'speaker_name': name, 'formal_claim': '具体观点'} for name in names]}
        for names in clusters]} for topic, clusters in topics]}}


def test_source_budget_distinguishes_same_topic_and_cross_topic():
    data = fixture([('甲题', [['媒体甲', '媒体乙']]), ('乙题', [['媒体甲', '媒体丙']])])
    assert approved_source_layout_issues(data) == []
    data['viewpoints']['by_topic'].append(fixture([('丙题', [['媒体甲', '媒体丁']])])['viewpoints']['by_topic'][0])
    assert any(x['code'] == 'source_report_use_limit' for x in approved_source_layout_issues(data))
    within = fixture([('甲题', [['媒体甲', '媒体乙'], ['媒体甲', '媒体丙']])])
    assert any(x['code'] == 'source_repeated_within_topic' for x in approved_source_layout_issues(within))


def test_single_source_is_valid_but_not_a_two_level_numbered_paragraph():
    from cwh_viewpoint_gate import numbered_clusters_allowed
    assert approved_source_layout_issues(fixture([('甲题', [['媒体甲']])])) == []
    data = fixture([('甲题', [['媒体甲'], ['媒体乙', '媒体丙']])])
    assert not numbered_clusters_allowed(data['viewpoints']['by_topic'][0]['clusters'])
    full = fixture([('甲题', [['媒体甲', '媒体丁'], ['媒体乙', '媒体丙']])])
    assert numbered_clusters_allowed(full['viewpoints']['by_topic'][0]['clusters'])
    before = copy.deepcopy(data)
    assert any(x['code'] == 'numbered_cluster_source_shortfall' for x in approved_source_layout_issues(data))
    assert data == before
    assert '每个一是/二是至少两个' in editorial_template_prompt('selection')


def test_author_and_reviewer_share_top_level_versus_cluster_heading_contract():
    from cwh_heading_quality import HEADING_REVIEW_PROMPT
    from cwh_writing_rules import writing_rules
    rule = writing_rules()['viewpoint']['approved_heading_rule']
    assert rule in HEADING_REVIEW_PROMPT
    assert rule in editorial_template_prompt('selection')
    assert '不新增实施效果' in rule and '分点标题' in rule
    assert '有replacement时检查replacement.text' in HEADING_REVIEW_PROMPT


def test_selection_separates_full_candidate_retention_from_formal_source_cap():
    from cwh_writing_rules import writing_rules
    from cwh_claim_synthesis import flat_prompt
    rule = writing_rules()['viewpoint']['selection_rule']
    assert '区分候选提取和正文取舍' in rule
    assert '正式正文同一议题只选该主体一项' in rule
    assert '其余有效判断保留备选' in rule
    assert '不要求机制相同' in rule
    assert '可分别进入对应观点簇' not in rule
    assert '不用同一宏观主题代替共同机制' not in rule
    prompt = flat_prompt(ranked=True)
    # The ID-only selector has no original articles. It receives selection
    # constraints, not the duplicated full-text extraction instructions.
    assert rule not in prompt
    for text in ('同一主体本题只选一条', '完整保留备选', '互补机制、条件和不同意见可以归组',
                 '不重新审核来源', '不同意见、必要限定'):
        assert text in prompt
    for ranked in (False, True):
        assert '"heading":"态度动词＋本题政策对象＋概括评价"' in flat_prompt(ranked=ranked)
        assert '"heading":"态度动词＋本组共同判断"' in flat_prompt(ranked=ranked)


def test_header_is_a_declared_display_mapping_not_count_reclassification():
    config = {'total_groups': {'domestic_mainstream': ['domestic_news']},
              'child_groups': {'domestic_mainstream': ['domestic_news']}}
    assert channel_display_labels(config)['domestic_mainstream'] == '境内新闻'
    config.update(channel_display_labels={'domestic_mainstream': '境内主流媒体'}, channel_display_label_basis='confirmed workbook formula')
    before = copy.deepcopy(config)
    assert channel_display_labels(config)['domestic_mainstream'] == '境内主流媒体'
    assert config == before


def test_domestic_difference_audit_separates_transfer_from_net_change():
    differences = [
        {'date': '2030-01-01', 'field': 'domestic_news', 'delta': 20},
        {'date': '2030-01-01', 'field': 'domestic_app', 'delta': -20},
        {'date': '2030-01-02', 'field': 'domestic_news', 'delta': 8},
        {'date': '2030-01-02', 'field': 'domestic_app', 'delta': -5},
        {'date': '2030-01-03', 'field': 'domestic_news', 'delta': None},
        {'date': '2030-01-04', 'field': 'overseas_news', 'delta': 2},
    ]
    before = copy.deepcopy(differences)
    assert domestic_difference_patterns(differences) == {
        'conserved_pair_days': 1, 'net_change_days': 1, 'unresolved_days': 1}
    assert differences == before
    assert domestic_difference_patterns([]) == {
        'conserved_pair_days': 0, 'net_change_days': 0, 'unresolved_days': 0}


def test_overseas_interpretations_keep_stance_and_separate_paragraphs():
    rows = [{'source': '事实媒体'+str(i), 'title_cn': '会议报道'+str(i), 'url': f'https://example.test/f{i}',
             'overseas_category': '事实性报道', 'formal_include': True, 'meeting_relevance': True}
            for i in range(4)]
    rows += [{'source': '解读媒体'+str(i), 'title_cn': '公共服务分析'+str(i), 'url': f'https://example.test/a{i}',
              'overseas_category': '解读性报道', 'formal_include': True, 'meeting_relevance': True,
              'summary_cn': '认为资金安排影响服务覆盖。分析师张某指出，地方资金安排仍有不确定性。'}
             for i in range(2)]
    data = {'appendices': {'overseas_reports': rows}}
    before = copy.deepcopy(data)
    paragraphs = overseas_media_body_paragraphs(data)
    assert len(paragraphs) == 3
    assert paragraphs[0].endswith('少量解读如下：')
    assert paragraphs[1].startswith('一是认为资金安排影响服务覆盖。解读媒体0《')
    assert paragraphs[2].startswith('二是认为资金安排影响服务覆盖。解读媒体1《')
    assert '分析师张某指出，地方资金安排仍有不确定性' in paragraphs[1]
    assert data == before
