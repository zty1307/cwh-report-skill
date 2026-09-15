import copy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_semantic_repairs import normalize_excluded_claims
from cwh_semantic_compiler import AUTHOR_PROMPT


def test_explicit_meeting_facts_cannot_become_viewpoints_by_eligible_envelope():
    fact = {'claim_kind': 'meeting_action_fact', 'claim': '会议通过某条例修订草案。'}
    original = [{'items': [{'id': 'current-id', 'decision': 'eligible', 'reason': '内容具体', 'claims': [fact]}]}]
    before = copy.deepcopy(original)
    result = normalize_excluded_claims(original)
    item = result[0]['items'][0]
    assert item['decision'] == 'excluded' and item['claims'] == []
    assert item['transport_exclusions'][0]['original_claims'] == [fact]
    assert original == before


def test_mechanisms_and_unmarked_legacy_claims_are_not_keyword_excluded():
    mechanism = {'claim_kind': 'policy_reasoning', 'claim': '完善适用条件可降低跨地区办事成本。'}
    legacy = {'claim': '修改条例需要衔接现有办理程序。'}
    source = [{'items': [{'decision': 'eligible', 'claims': [mechanism, legacy]}]}]
    assert normalize_excluded_claims(source) == source
    assert '原话正确或独立核验支持，都不能替代解读资格' in AUTHOR_PROMPT


def test_topic_manifest_survives_transport_and_prompt_requires_policy_object_disambiguation():
    from run_cwh_compiled_worker import semantic_packet
    source = {'topic': '制度清理', 'agenda_topics': ['制度清理', '某住房条例修订'], 'items': []}
    assert semantic_packet(source)['agenda_topics'] == source['agenda_topics']
    assert '不为补齐薄弱议题搬用其他议题的成熟解读' in AUTHOR_PROMPT
