import unittest
from opinion_gate_v8 import argument_atom,select
from test_priority_screen import source,AGENDA

class OptimizedQueueContracts(unittest.TestCase):
    def test_exact_utterance_dedup_ignores_title_prefix_not_speaker(self):
        core='数据产权标准不统一增加了跨区域流通成本，需要完善登记制度，避免企业反复办理相同手续。'
        a=argument_atom('某研究院研究员张三表示，'+core)
        b=argument_atom('张三表示，'+core)
        c=argument_atom('某大学教授李四表示，'+core)
        self.assertEqual(a['key'],b['key']);self.assertNotEqual(a['key'],c['key'])

    def test_conditions_and_different_judgments_not_erased(self):
        a=argument_atom('如果满足缴存年限，某研究院研究员张三表示，制度改革可以提高资源配置效率，并减少企业跨区域登记成本。')
        b=argument_atom('某研究院研究员张三表示，制度改革可以提高资源配置效率，并减少企业跨区域登记成本。')
        self.assertNotEqual(a['key'],b['key'])
        c=argument_atom('某研究院研究员张三表示，接口标准需要统一，否则不同地区的数据平台无法互相连接，导致重复建设和资金浪费。')
        self.assertNotEqual(b['key'],c['key'])

    def test_complete_articles_cap_and_unread_reserves(self):
        rows=[source(i)for i in range(5)]
        chosen,audit,summary,_=select(rows,AGENDA,max_articles=1)
        self.assertEqual(1,len(chosen));self.assertIn(chosen[0],rows)
        self.assertEqual(4,summary['reserve_articles']);self.assertTrue(all(r['unread']for r in audit))
        self.assertTrue(all(r['decision']in {'reserve','primary_full_text'}for r in audit))
        with self.assertRaises(ValueError):select(rows,AGENDA,max_articles=100)

    def test_character_budget_never_truncates(self):
        chosen,audit,_,_=select([source(1)],AGENDA,max_body_chars=1)
        self.assertFalse(chosen);self.assertEqual('reserve',audit[0]['decision'])
    def test_cost_profile_is_explicit_and_cannot_change_source_text(self):
        rows=[source(i)for i in range(5)]
        chosen,_,summary,_=select(rows,AGENDA,max_articles=3,reading_cost_power=1,exploration_cost_power=.65)
        self.assertEqual(1,summary['priority_limits']['reading_cost_power'])
        self.assertTrue(all(row in rows for row in chosen))
        with self.assertRaises(ValueError):select(rows,AGENDA,reading_cost_power=float('nan'))

if __name__=='__main__':unittest.main()
