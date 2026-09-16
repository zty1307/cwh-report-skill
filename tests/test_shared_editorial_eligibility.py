"""Selection eligibility reaches independent review, not only original author."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_writing_rules import editorial_eligibility_prompt, writing_rules
from cwh_semantic_compiler import AUTHOR_PROMPT
from cwh_semantic_repairs import REPAIR_PROMPT
from cwh_author_batches import synthesis_prompt
from run_cwh_compiled_worker import REVIEW_PROMPT


def test_author_synthesis_repair_and_reviewer_share_editorial_criteria():
    rule = editorial_eligibility_prompt()
    assert all(rule in prompt for prompt in (AUTHOR_PROMPT, REPAIR_PROMPT, synthesis_prompt(), REVIEW_PROMPT))
    assert all(row['description'] in rule for row in writing_rules()['viewpoint']['editorial_exclusions'])
    assert '不能因出现产业链、投资、受益等词就删除' in rule


def test_unsupported_selection_has_no_host_fabricated_revision():
    assert '按本题正式选材资格判unsupported并明确理由，revision=null' in REVIEW_PROMPT
    assert '存在真实受支持的合格分析但当前表述越界时' in REVIEW_PROMPT
