"""Check evidence-boundary behavior behind the recovery experiment."""
import unittest
import portable_screen as p
from recover_more_views import normalize
from test_portable_screen import source, view, AGENDA

class RecoveryContracts(unittest.TestCase):
    def long_source(self):
        return source(text='某大学教授张三认为，'+('数字基础设施需要跨区域协调标准，避免重复建设增加成本。'*40))

    def test_short_claim_is_not_automatically_rejected_or_approved(self):
        r=source();v=view(r)
        v['claim']='算力资源供需错配增加企业成本，跨区域调度需要统一接口标准，以减少设备闲置。'
        self.assertIn('claim_length_needs_edit',p.format_view(r,v,AGENDA)['errors'])
        x=normalize(r,v,AGENDA)
        self.assertNotIn('claim_length_needs_edit',x['errors'])
        self.assertFalse(x['formal_ready'])
        self.assertEqual(v['claim'],x['claim'])

    def test_adjacent_list_becomes_exact_continuous_range(self):
        r=self.long_source();v=view(r);s=p.segments(r)
        v['evidence']=[q['id'] for q in s[:3]]
        x=normalize(r,v,AGENDA)
        self.assertEqual(v['claim'],x['claim'])
        self.assertEqual(''.join(q['text'] for q in s[:3]),x['excerpt'])
        self.assertEqual(x['repair_proposals'][0]['type'],'contiguous_list_canonicalized')
        self.assertFalse(x['formal_ready'])

    def test_nonadjacent_list_includes_intervening_text_and_requires_review(self):
        r=self.long_source();v=view(r);s=p.segments(r)
        v['evidence']=[s[0]['id'],s[2]['id'],s[3]['id']]
        x=normalize(r,v,AGENDA)
        self.assertEqual(''.join(q['text'] for q in s[:4]),x['excerpt'])
        self.assertIn(s[1]['text'],x['excerpt'])
        self.assertEqual(x['repair_proposals'][0]['type'],'continuous_context_envelope_requires_independent_review')
        self.assertFalse(x['formal_ready'])

    def test_cross_article_and_reversed_lists_are_not_fixed(self):
        r=self.long_source();v=view(r);s=p.segments(r)
        for ids in [[s[0]['id'],'r2:p2',s[2]['id']], [s[2]['id'],s[1]['id'],s[0]['id']]]:
            v['evidence']=ids;x=normalize(r,v,AGENDA)
            self.assertEqual(ids,x['evidence']);self.assertTrue(x['errors'])

if __name__=='__main__':unittest.main()
