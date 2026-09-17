"""Cross-meeting prompt routing, not a semantic quality or full-run certificate."""
import copy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_writing_rules import editorial_template_prompt, writing_rules
from cwh_article_reading import reading_prompt
from cwh_claim_synthesis import flat_prompt
from cwh_model_contract import build_task_payload


def test_only_reading_receives_fictitious_composition_example():
    rules = writing_rules()['viewpoint']
    prompt = reading_prompt()
    assert rules['claim_unit_rule'] in prompt
    assert rules['composition_example']['source'] in prompt
    assert '虚构写法示范，不是报告事实' in prompt
    assert rules['paragraph_pairing_rule'] not in prompt
    assert '一位主体一句完整观点' not in prompt


def test_source_reasoning_checks_are_shared_by_author_and_reviewer():
    from run_cwh_compiled_worker import REVIEW_PROMPT
    rule = writing_rules()['viewpoint']['source_reasoning_quality_rule']
    assert rule in reading_prompt()
    assert rule in REVIEW_PROMPT
    assert '正面与批评用同一标准' in rule
    assert '不能擅自修正作者数字' in rule
    assert REVIEW_PROMPT.startswith('先检查论据是否自洽')
    assert '不能加“作者认为/原文据此认为”' in REVIEW_PROMPT


@pytest.mark.parametrize('ranked', [False, True])
def test_both_selection_modes_use_shared_pairing_without_rewriting_claims(ranked):
    rules = copy.deepcopy(writing_rules()['viewpoint'])
    rules['paragraph_pairing_rule'] = 'configured-complementary-voices'
    prompt = flat_prompt(rules, ranked=ranked)
    assert 'configured-complementary-voices' in prompt
    assert rules['composition_example']['source'] not in prompt
    assert '不合并或改写claim' in prompt or '不得改写claim' in prompt


def test_revision_uses_frames_but_not_fictitious_source():
    prompt = editorial_template_prompt('revision')
    assert writing_rules()['viewpoint']['claim_unit_rule'] in prompt
    assert writing_rules()['viewpoint']['composition_example']['source'] not in prompt
    assert '没有依据的槽位整项省略' in prompt


def test_manual_worker_contract_receives_same_general_templates(tmp_path):
    rules = copy.deepcopy(writing_rules())
    rules['viewpoint']['claim_unit_rule'] = 'configured-unit'
    rules['viewpoint']['composition_frames'] = ['configured-frame']
    rules['viewpoint']['paragraph_pairing_rule'] = 'configured-pairing'
    with patch('cwh_model_contract.writing_rules', return_value=rules):
        task = build_task_payload(stage_id='domestic_viewpoints', task_type='analysis_bundle',
            expected_output=tmp_path / 'author.json', inputs={}, rules=[], profile_name='bounded_60m')
    assert task['writing_handoff']['claim_unit_rule'] == 'configured-unit'
    assert task['writing_handoff']['composition_frames'] == ['configured-frame']
    assert task['writing_handoff']['paragraph_pairing_rule'] == 'configured-pairing'


def test_unknown_stage_is_not_silently_given_inapplicable_examples():
    with pytest.raises(ValueError):
        editorial_template_prompt('sentiment')


def test_frames_do_not_contain_period_specific_models_or_baseline_accounts():
    text = editorial_template_prompt('claim') + editorial_template_prompt('selection')
    for forbidden in ('2026', 'deepseek', 'hy4', 'glm', '户外求索', '专聊房君', '7月31', '5月15'):
        assert forbidden not in text
