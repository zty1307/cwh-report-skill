import tempfile,unittest
from pathlib import Path
from portable_screen import load,save,prepare,digest
from benchmark_recall_periods import prepare_review,ingest_review
from test_priority_screen import source,AGENDA

class CrossPeriodContracts(unittest.TestCase):
    def fixture(self,root,count=37):
        row=source(1);prepare([row],AGENDA,root/'model',90000,'fake-unrun')
        v={'id':'r1','topic':AGENDA['topics'][0],'kind':'account','name':'示例号','role':'',
           'claim':'数据产权标准不统一增加跨区域流通成本，登记制度之间缺乏衔接会增加企业重复办理的成本。',
           'evidence':['r1:p1'],'identity':[],'source_kind':'original','attribution':'explicit','original_date':'','date_evidence':[],'errors':[]}
        save(root/'model/views.json',[{**v,'claim':v['claim']+str(i)} for i in range(count)])
        prepare_review(root/'model',root/'review');return row

    def test_all_nominations_reviewed_no_thirty_cap(self):
        with tempfile.TemporaryDirectory() as f:
            root=Path(f);row=self.fixture(root);task=load(root/'review/tasks/review-001.json')
            self.assertEqual(37,len(task['expected_candidate_ids']))
            self.assertEqual(1,len(task['articles']))
            self.assertEqual(row['content'],''.join(p['text'] for p in task['articles'][0]['paragraphs']))
            self.assertEqual(37,len(ingest_review(root/'review')['unreviewed']))

    def test_task_tamper_refused(self):
        with tempfile.TemporaryDirectory() as f:
            root=Path(f);self.fixture(root);p=root/'review/tasks/review-001.json';v=load(p)
            v['articles'][0]['paragraphs'][0]['text']='只读节选';save(p,v)
            with self.assertRaises(ValueError):ingest_review(root/'review')

    def test_partial_response_keeps_unreviewed_and_never_formal(self):
        with tempfile.TemporaryDirectory() as f:
            root=Path(f);self.fixture(root);task=load(root/'review/tasks/review-001.json')
            save(root/'review/responses/review-001.json',{'items':[{'candidate_id':task['expected_candidate_ids'][0],
                 'decision':'exclude','reason':'假宿主测试','original_date':'','date_evidence':[]}]})
            s=ingest_review(root/'review');self.assertEqual(36,len(s['unreviewed']));self.assertEqual(0,s['formal_ready']);self.assertEqual(0,s['source_check_claims'])

if __name__=='__main__':unittest.main()
