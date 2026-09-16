"""Reading-only batches cannot skip final native selection or source gates."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_article_reading import reading_prompt, reading_contract


def test_reading_contract_does_not_request_provisional_topic_composition():
    prompt = reading_prompt()
    assert '不输出cluster、heading、clusters' in prompt
    assert 'quote_range' in prompt and 'published_at' in prompt
    assert 'actual_model' not in prompt
    contract = reading_contract({'items': [{'id': 'r1'}, {'id': 'w2'}]})
    assert '["r1","w2"]' in contract


def test_production_reading_prompt_matches_the_tested_semantic_scope():
    prompt = reading_prompt()
    assert '单纯说明会议首次核准' in prompt
    assert '本阶段不写标题、不分组、不选最终声音数' in prompt
    assert '完整年' in prompt or '连续完整年月日' in prompt
