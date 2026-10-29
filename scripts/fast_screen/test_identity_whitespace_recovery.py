import unittest,hashlib
from portable_screen import segments,format_view
from recover_identity_whitespace import recover
from test_portable_screen import AGENDA

class IdentityWhitespaceContracts(unittest.TestCase):
    def fixture(self,text='某大学教授王 \n 伟认为，算力资源供需错配增加企业使用成本，跨区域调度需要统一接口标准，以减少设备闲置。'):
        r={'id':'r1','content':text};ids=[x['id']for x in segments(r)]
        v={'topic':AGENDA['topics'][0],'kind':'person','name':'王伟','role':'某大学教授',
           'claim':'算力资源供需错配增加企业使用成本，跨区域调度需要统一接口标准，以减少设备闲置并降低使用成本，提高资源配置效率。',
           'identity':[ids[0],ids[-1]],'evidence':[ids[0],ids[-1]],'source_kind':'original','attribution':'explicit','original_date':'','date_evidence':[]}
        x=format_view(r,v,AGENDA);x.update(independent_decision='retain',candidate_id='r1:1')
        return r,x

    def test_only_whitespace_recovered_semantics_preserved(self):
        r,v=self.fixture();x=recover(r,v);self.assertIsNotNone(x)
        for k in ['claim','name','role','evidence','identity','excerpt','source_sha256','independent_decision','original_date']:
            self.assertEqual(v[k],x[k])
        self.assertEqual(['identity_name_not_in_anchor'],v['errors'])
        self.assertEqual([],x['errors']);self.assertFalse(x['formal_ready'])

    def test_missing_real_name_not_recovered(self):
        r,v=self.fixture('某大学教授王强认为，算力资源供需错配增加企业使用成本。')
        self.assertIsNone(recover(r,v))

    def test_other_errors_or_missing_independent_review_not_recovered(self):
        r,v=self.fixture();v['errors'].append('missing_institution');self.assertIsNone(recover(r,v))
        r,v=self.fixture();v['independent_decision']='needs_rewrite';self.assertIsNone(recover(r,v))

    def test_changed_source_refused(self):
        r,v=self.fixture();r['content']+='改动'
        with self.assertRaises(ValueError):recover(r,v)

if __name__=='__main__':unittest.main()
