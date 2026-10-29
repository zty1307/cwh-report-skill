import tempfile,unittest,json
from pathlib import Path
from portable_screen import save,load
import test_compact_screen_transport as fixtures
from compact_screen_transport import decode
from portable_screen import prepare,ingest
from benchmark_recall_periods import prepare_review
from run_optimized_screen import schema_packets
from collect_samples import export_collection
from review_selected_candidates import prepare_selection
from workbuddy_screen_host import answer_text

class CollectionContracts(unittest.TestCase):
    def test_error_result_does_not_fall_back_to_assistant_answer(self):
        with self.assertRaises(ValueError):answer_text('{"type":"assistant","message":{"content":[{"type":"text","text":"{}"}]}}\n{"type":"result","subtype":"error_max_turns","is_error":true}')
    def test_collection_and_selected_review_preserve_full_body_and_pending(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);fixture=fixtures.CompactTransportContracts();p=fixture.packet()
            row={'id':'r19','title':'原题','account':'原账号','content':'完整原文一。\n完整原文二。','published_at':'2026-07-31','url':''}
            agenda={'topics':['议题甲','议题乙'],'topic_aliases':[[],[]],'window_start':'2026-07-31','window_end':'2026-08-03'}
            prepare([row],agenda,root/'model',90000,'fake',mode='recall_v8')
            # A deliberately invalid identity/short claim must remain pending.
            answer={'items':[{'id':'r19','code':'has_view','views':[{'topic':'议题乙','kind':'person','name':'张三','role':'某大学教授',
                'identity':[],'source_kind':'unclear','attribution':'uncertain','claim':'确有分析但身份未核。','evidence':['r19:p1','r19:p1'],'original_date':'','date_evidence':[]}]}]}
            save(root/'model/responses/read-001.json',answer);ingest(root/'model')
            prepare_review(root/'model',root/'queue');schema_packets(root/'queue')
            state=export_collection(root/'model',root/'queue',root/'results')
            self.assertEqual(1,state['nominations']);self.assertEqual(0,state['independently_reviewed'])
            v=load(root/'results/nominations_pending_review.json')[0]
            self.assertFalse(v['formal_ready']);self.assertEqual('unreviewed',v['independent_decision'])
            prepare_selection(root/'queue',['r19:1'],root/'selected')
            task=load(root/'selected/tasks/review-001.json')
            self.assertEqual(row['content'],''.join(s['text']for s in task['articles'][0]['paragraphs']))
            self.assertEqual(['r19:1'],task['expected_candidate_ids'])
            with self.assertRaises(ValueError):prepare_selection(root/'queue',['missing'],root/'invalid')

if __name__=='__main__':unittest.main()
