import json,tempfile,unittest
from pathlib import Path
import portable_screen as p
from opinion_gate import select
from priority_review_plan import prepare as review_plan,ingest as review_ingest

AGENDA={'topics':['数字中国建设'],'topic_aliases':[['数据产权','数字中国']],
    'window_start':'2026-07-10 00:00:00','window_end':'2026-07-13 13:30:00'}
def source(n):
    return {'id':f'r{n}','title':f'数字中国分析{n}','account':'示例号','published_at':'2026-07-11 12:00:00',
        'content':f'某研究院研究员王甲认为，数字中国的数据产权标准不一、跨区域制度衔接不足，导致企业数据流通成本过高，需要建立统一登记机制并协调各地授权规则，避免重复登记。本文讨论对象编号{n}。\n完整尾部不应删除。','url':'https://example.invalid/'+str(n)}

class Contracts(unittest.TestCase):
    def test_priority_cap_and_complete_bodies(self):
        rows=[source(n)for n in range(5)];chosen,audit,summary,_=select(rows,AGENDA,max_articles=1)
        self.assertEqual(1,len(chosen));self.assertEqual(chosen[0],next(r for r in rows if r['id']==chosen[0]['id']))
        self.assertEqual(4,summary['reserve_articles']);self.assertFalse(any(r['decision']=='exclude'for r in audit))
        with self.assertRaises(ValueError):select(rows,AGENDA,max_articles=100)
    def test_budget_is_unread_not_semantic_rejection(self):
        selected,audit,_,_=select([source(1)],AGENDA,max_body_chars=1)
        self.assertFalse(selected);self.assertTrue(audit[0]['unread']);self.assertEqual('reserve',audit[0]['decision'])
    def fixture(self,root,n=35):
        rows=[source(1)];p.prepare(rows,AGENDA,root,90000,'fake-unrun',mode='focused')
        p.ingest(root);p.save(root/'views.json',[{'id':'r1','topic':AGENDA['topics'][0],'kind':'person','name':f'王甲{i}','role':'某研究院研究员',
            'claim':f'数据产权标准不统一增加了跨区域流通成本，需要完善登记制度。{i}','excerpt':rows[0]['content'],
            'evidence':['r1:p1','r1:p1'],'identity':['r1:p1','r1:p1'],'source_kind':'original','attribution':'explicit','original_date':'','date_evidence':[],
            'errors':[],'report_sentence':f'某研究院研究员王甲{i}认为，需完善制度。'}for i in range(n)])
        return rows
    def test_focused_policy_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);self.fixture(root,1);task=p.load(root/'tasks/read-001.json')
            self.assertIn('严格优先提名',task['policy']);task['policy']=p.POLICY;p.save(root/'tasks/read-001.json',task)
            with self.assertRaises(ValueError):p.ingest(root)
    def test_review_cap_sources_once_and_no_duplicated_quotes(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);rows=self.fixture(root/'model');out=root/'review';s=review_plan(root/'model',out)
            self.assertEqual(30,s['selected_for_independent_review']);self.assertEqual(5,s['unreviewed_reserve'])
            packet=p.load(out/'tasks/review-001.json');self.assertEqual(1,len(packet['articles']))
            article=packet['articles'][0];self.assertEqual(rows[0]['content'],''.join(v['text']for v in article['paragraphs']))
            self.assertNotIn('excerpt',article['nominations'][0]);self.assertNotIn('role_excerpt',article['nominations'][0])
            self.assertFalse(review_ingest(out)['complete_selected_review'])
            nominations=p.load(out/'selected_nominations.json')
            p.save(out/'responses/review-001.json',{'items':[{'candidate_id':v['candidate_id'],'decision':'retain','reason':'待核原网页','original_date':'','date_evidence':[]}for v in nominations]})
            done=review_ingest(out);self.assertTrue(done['complete_selected_review']);self.assertEqual(0,done['formal_ready'])
            packet['articles'][0]['nominations'][0].pop('claim');p.save(out/'tasks/review-001.json',packet)
            with self.assertRaises(ValueError):review_ingest(out)

if __name__=='__main__':unittest.main()
