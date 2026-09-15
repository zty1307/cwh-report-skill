"""Cross-period invariants, not a stored historical report answer."""
import copy
import re
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from formalize_cwh_report import md_table, formal_overseas_summary
from raw_system_workbook_pipeline import validate_declared_topic_mapping, PipelineError
from raw_system_workbook_pipeline import build_normalized_bundle, build_overseas_review_packet
from cwh_writing_rules import writing_rules


def test_markdown_table_escapes_cell_pipes_without_changing_original_values():
    headers = ['来源', '标题|原文']
    rows = [['真实机构', '政策观察 | 实施条件\n及风险']]
    original = copy.deepcopy(rows)
    text = md_table(headers, rows)
    assert rows == original
    assert '政策观察 \\| 实施条件 及风险' in text
    assert all(len(re.findall(r'(?<!\\)\|', line)) == 3 for line in text.splitlines())


def test_long_reviewed_summary_retains_final_condition_without_changing_source():
    summary = '有关政策可改善资源配置，但其实际效果取决于配套实施机制。' * 12 + '只有满足安全条件时才可能实现，不代表已经发生。'
    row = {'summary_cn_simplified': summary}
    original = copy.deepcopy(row)
    value = formal_overseas_summary(row)
    assert len(value) > 260 and value.endswith('不代表已经发生')
    assert row == original


@pytest.mark.parametrize('metadata', [
    {'topic_mapping_basis': '按议程与编号顺序推断'},
    {'topic_mapping_basis': 'Assumed from ordinal filenames'},
    {'topic_mapping_basis': 'inferred mapping'},
    {'topic_mapping_confirmed': False},
    {'topic_mapping_status': 'pending_review'},
    {'topic_mapping_status': 'unconfirmed', 'topic_mapping_confirmed': True},
])
def test_known_unconfirmed_mapping_fails_before_reading_workbooks(metadata):
    original = copy.deepcopy(metadata)
    with pytest.raises(PipelineError, match='topic_mapping_requires_confirmation'):
        build_normalized_bundle(None, {}, metadata)
    assert metadata == original


@pytest.mark.parametrize('metadata', [
    {'topic_titles': ['政策甲', '政策乙']},
    {'topic_mapping_basis': '本期导出查询身份记录'},
    {'topic_mapping_basis': '原推断已经由用户逐组确认', 'topic_mapping_confirmed': True,
     'topic_mapping_status': 'confirmed'},
])
def test_explicit_legacy_titles_or_actual_confirmation_remain_compatible(metadata):
    original = copy.deepcopy(metadata)
    validate_declared_topic_mapping(metadata)
    assert metadata == original


def test_raw_and_supplemental_overseas_routes_receive_same_formal_summary_rule():
    import cwh_overseas_semantics
    packet = build_overseas_review_packet([], {}, {}, [])
    rule = writing_rules()['overseas']['interpretive_summary_rule']
    assert rule in packet['instructions'] and rule in cwh_overseas_semantics.PROMPT
