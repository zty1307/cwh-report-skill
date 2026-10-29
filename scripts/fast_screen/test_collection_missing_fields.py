import copy,unittest
from portable_screen import format_view,segments
from recover_more_views import normalize
from test_priority_screen import source,AGENDA

class MissingFieldIsolation(unittest.TestCase):
    def fixture(self):
        row=source(1);ids=[s['id']for s in segments(row)]
        view={'topic':AGENDA['topics'][0],'kind':'account','name':row.get('account','示例号'),'role':'',
            'claim':'数据产权标准不统一会增加跨区域流通成本，需要完善登记制度并减少企业反复办理相同手续的成本，提高资源配置效率。',
            'evidence':[ids[0],ids[-1]],'identity':[],'source_kind':'original','attribution':'explicit','original_date':''}
        return row,view
    def test_missing_empty_date_anchor_is_unknown_not_invented(self):
        row,v=self.fixture();raw=format_view(row,v,AGENDA);before=copy.deepcopy(raw);result=normalize(row,raw,AGENDA)
        self.assertEqual(before,raw);self.assertEqual([],result['date_evidence']);self.assertEqual('',result['original_date'])
        self.assertFalse(result['errors']);self.assertTrue(result['pending_original_date']);self.assertFalse(result['formal_ready'])
        self.assertTrue(any(x['type']=='explicit_empty_date_defaults_unknown_anchor'for x in result['repair_proposals']))
    def test_known_date_without_anchor_cannot_be_approved(self):
        row,v=self.fixture();v['original_date']=AGENDA['window_start'][:10]
        result=normalize(row,format_view(row,v,AGENDA),AGENDA)
        self.assertIn('date_anchor_missing',result['errors']);self.assertIn('missing_model_field:date_evidence',result['errors'])
        self.assertFalse(result['report_sentence']);self.assertFalse(result['formal_ready'])
    def test_other_missing_required_field_is_retained_pending_not_crash(self):
        row,v=self.fixture();del v['claim'];result=normalize(row,format_view(row,v,AGENDA),AGENDA)
        self.assertIn('missing_model_field:claim',result['errors']);self.assertFalse(result['report_sentence'])

if __name__=='__main__':unittest.main()
