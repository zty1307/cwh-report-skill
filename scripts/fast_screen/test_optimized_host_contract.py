import tempfile,unittest
from pathlib import Path
from portable_screen import load,save,prepare,ingest,POLICY
from run_optimized_screen import schema_packets,complete_pool
from benchmark_recall_periods import prepare_review,ingest_review
from test_priority_screen import source,AGENDA

class OptimizedHostContracts(unittest.TestCase):
    def test_new_policy_is_opt_in_and_keeps_legacy_mode(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);prepare([source(1)],AGENDA,root/'new',90000,'fake',mode='recall_v8')
            task=load(root/'new/tasks/read-001.json')
            self.assertIn('预计、可能',task['policy']);self.assertIn('不同实质判断',task['policy'])
            prepare([source(1)],AGENDA,root/'old',90000,'fake')
            self.assertEqual(POLICY,load(root/'old/tasks/read-001.json')['policy'])

    def test_generic_review_host_has_sealed_output_schema(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);prepare([source(1)],AGENDA,root/'model',90000,'fake',mode='recall_v8')
            ingest(root/'model')
            save(root/'model/views.json',[{'id':'r1','topic':AGENDA['topics'][0],'kind':'account','name':'示例号','role':'',
              'claim':'数据产权标准不统一会增加跨区域流通成本，需要完善登记制度，并减少企业重复办理相同手续的成本。',
              'evidence':['r1:p1'],'identity':[],'source_kind':'original','attribution':'explicit','original_date':'','date_evidence':[],'errors':[]}])
            prepare_review(root/'model',root/'review');schema_packets(root/'review')
            task=load(root/'review/tasks/review-001.json')
            self.assertEqual(load(root/'review/response_schema.json'),task['output_schema'])
            self.assertEqual(['r1:1'],ingest_review(root/'review')['unreviewed'])
            pool=complete_pool(root/'review',root/'results')
            self.assertEqual(1,pool['pending_unreviewed']);self.assertEqual(0,pool['source_check_claims'])
            self.assertEqual('unreviewed',load(root/'results/pending_candidates.json')[0]['independent_decision'])
            task['output_schema']={'type':'string'};save(root/'review/tasks/review-001.json',task)
            with self.assertRaises(ValueError):ingest_review(root/'review')

if __name__=='__main__':unittest.main()
