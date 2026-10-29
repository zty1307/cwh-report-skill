import copy,unittest
import tempfile
from pathlib import Path
from portable_screen import prepare,load
from test_priority_screen import source
from canonical_screen_transport import encode
from test_portable_screen import AGENDA

class ReadableTransportContracts(unittest.TestCase):
    def test_article_cap_keeps_full_sources_and_complete_id_coverage(self):
        rows=[source(i)for i in range(5)]
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);prepare(rows,AGENDA,root,90000,'fake',mode='recall_v8',max_articles_per_batch=2)
            packets=[load(p)for p in sorted((root/'tasks').glob('*.json'))]
            self.assertEqual([2,2,1],[len(p['articles'])for p in packets])
            self.assertEqual([r['id']for r in rows],[id for p in packets for id in p['expected_article_ids']])
            for p in packets:
                for a in p['articles']:
                    original=next(r for r in rows if r['id']==a['id'])
                    self.assertEqual(original['content'],''.join(x['text']for x in a['paragraphs']))
    def test_complete_sources_and_policy_not_rewritten(self):
        packet={'policy':'原文条件必须保留','agenda':AGENDA,'articles':[{'id':'r1','paragraphs':[{'id':'r1:p1','text':'完整原文首尾均保留。'}]}],
                'expected_article_ids':['r1']};before=copy.deepcopy(packet);api=encode(packet)
        self.assertEqual(before,packet);self.assertEqual(packet['articles'],api['articles']);self.assertEqual(packet['policy'],api['policy'])
        self.assertIn('views',api['output_schema']['properties']['items']['items']['properties'])
    def test_review_schema_cannot_be_silently_regenerated(self):
        packet={'expected_candidate_ids':['r1:1'],'policy':'必须独立复核','articles':[]}
        with self.assertRaises(ValueError):encode(packet)
        packet['output_schema']={'type':'object'};self.assertEqual(packet,encode(packet))

if __name__=='__main__':unittest.main()
