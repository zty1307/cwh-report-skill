from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_writing_rules import editorial_eligibility_prompt, writing_rules
from cwh_article_reading import reading_prompt
from run_cwh_compiled_worker import REVIEW_PROMPT


def test_same_plain_language_reasoning_boundary_reaches_author_and_reviewer():
    rule = writing_rules()['viewpoint']['public_reasoning_boundary_rule']
    assert rule in editorial_eligibility_prompt()
    assert rule in reading_prompt()
    assert rule in REVIEW_PROMPT
    assert '已证实的普遍事实' in rule
    assert '同一证据标准' in rule


def test_reviewer_distinguishes_missing_support_from_ambiguous_object():
    assert '本条全部excerpt_segments' in REVIEW_PROMPT
    assert '语境指代不清与论据缺失分别说明' in REVIEW_PROMPT
    assert '否则revision必须是对象' not in REVIEW_PROMPT
