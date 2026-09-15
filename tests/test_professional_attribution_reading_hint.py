"""Reading order signals never certify policy relevance or quote eligibility."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_cwh_corpus_index import professional_quote_hint


def test_named_professional_telling_outlet_is_not_missed():
    text = '研究院首席专家赵明对某财经媒体记者表示，物流体系改革须改善标准协同。'
    assert professional_quote_hint(text, ['物流体系']) == 1


def test_later_attribution_reuses_explicit_role_in_same_article():
    text = ('研究员、某智库理事长赵明对报社记者表示，产业需因地制宜。'
            + '背景材料。' * 180
            + '赵明指出，物流体系改革须兼顾数据共享和企业成本。')
    assert professional_quote_hint(text, ['物流体系']) == 1


def test_title_or_unrelated_role_does_not_certify_hint():
    assert professional_quote_hint('专家解读：赵明表示，物流体系改革需协同。', ['物流体系']) == 0
    assert professional_quote_hint('教授赵明表示，天气很好。', ['物流体系']) == 0


def test_hint_remains_capped_and_handles_direct_attribution():
    text = '教授赵明认为，物流体系需要协同。' * 8
    assert professional_quote_hint(text, ['物流体系']) == 3


def test_interview_bridge_and_expert_committee_role_are_recognized():
    text = '某经济专家委员会委员赵明在接受财经媒体记者采访时表示，物流体系需协同。'
    assert professional_quote_hint(text, ['物流体系']) == 1
