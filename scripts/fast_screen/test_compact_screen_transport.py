import copy,unittest,tempfile,subprocess,sys,json
from pathlib import Path
from portable_screen import save,digest
from compact_screen_transport import encode,decode,compress_known_response
from recall_v8_policy import EXTRACTION_POLICY
from portable_screen import load_response

class CompactTransportContracts(unittest.TestCase):
    def test_fence_removed_but_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory()as d:
            path=Path(d)/'answer.txt';path.write_text('```json\n{"items":[]}\n```',encoding='utf-8')
            self.assertEqual(({'items':[]},['single_markdown_fence_removed']),load_response(path))
            path.write_text('{"items":[],"items":[1]}',encoding='utf-8')
            with self.assertRaises(ValueError):load_response(path)
    def packet(self):
        return {'policy':EXTRACTION_POLICY,'agenda':{'topics':['议题甲','议题乙']},'expected_article_ids':['r19'],
            'articles':[{'id':'r19','title':'原题','account':'原账号','published_at':'2026-07-31',
                         'paragraphs':[{'id':'r19:p1','text':'完整原文一。\n'},{'id':'r19:p2','text':'完整原文二。'}]}]}
    def answer(self):
        return {'items':[{'i':'r19','c':'h','g':[{'t':'议题乙','k':'p','n':'张三','r':'某大学教授','i':[1],
            's':'r','a':True,'q':[{'c':'预计在满足条件后产生影响，不把可能结果当成事实。','e':[1,2],'d':'','x':[]},
                               {'c':'另一条不同的完整判断，机构职务不需重复抄写。','e':[2],'d':'2026-07-31','x':[2]}]}]}]}
    def test_source_unchanged_and_all_claims_expanded(self):
        p=self.packet();api=encode(p);self.assertEqual(p['articles'],api['articles'])
        x=decode(p,self.answer())['items'][0]['views'];self.assertEqual(2,len(x))
        self.assertEqual('议题乙',x[0]['topic']);self.assertEqual('某大学教授',x[1]['role'])
        self.assertEqual(['r19:p1','r19:p2'],x[0]['evidence']);self.assertEqual('2026-07-31',x[1]['original_date'])
        self.assertEqual(self.answer()['items'][0]['g'][0]['q'][0]['c'],x[0]['claim'])
    def test_invalid_topic_paragraph_and_duplicate_article_refused(self):
        for field,value in [('t',99),('i',[99])]:
            r=self.answer();r['items'][0]['g'][0][field]=value
            with self.assertRaises(ValueError):decode(self.packet(),r)
        r=self.answer();r['items']*=2
        with self.assertRaises(ValueError):decode(self.packet(),r)
    def test_known_response_roundtrip_preserves_all_semantic_fields_and_order(self):
        p=self.packet();original=decode(p,self.answer());compressed=compress_known_response(p,original)
        self.assertEqual(original,decode(p,compressed))
    def test_category_conflict_is_preserved_for_localized_canonical_validation(self):
        r=self.answer();r['items'][0]['c']='t'
        item=decode(self.packet(),r)['items'][0]
        self.assertEqual('trading_only',item['code']);self.assertEqual(2,len(item['views']))
    def test_review_ids_dates_and_decisions_losslessly_restored(self):
        p=self.packet();p['expected_candidate_ids']=['r19:7','r19:8']
        p['articles'][0]['nominations']=[{'candidate_id':'r19:7','claim':'原观点甲'},{'candidate_id':'r19:8','claim':'原观点乙'}]
        api=encode(p);self.assertEqual([1,2],api['expected_candidate_ids'])
        self.assertEqual(p['articles'][0]['paragraphs'],api['articles'][0]['paragraphs'])
        out=decode(p,{'items':[{'i':2,'d':'w','r':'漏掉条件','t':'','e':[]},{'i':1,'d':'r','r':'原文支持','t':'2026-07-31','e':[2]}]})
        self.assertEqual('r19:8',out['items'][0]['candidate_id']);self.assertEqual('needs_rewrite',out['items'][0]['decision'])
        self.assertEqual(['r19:p2'],out['items'][1]['date_evidence'])
    def test_cli_bridge_with_fake_host_preserves_sources_and_records_receipt(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);bridge=Path(__file__).with_name('compact_screen_transport.py')
            host=root/'host.py';answer=self.answer()
            host.write_text('import json,sys\np=json.load(sys.stdin)\nassert p["articles"][0]["paragraphs"][0]["text"]=="完整原文一。\\n"\nprint('+repr(json.dumps(answer,ensure_ascii=False))+')',encoding='utf-8')
            manifest=root/'manifest.json';save(manifest,{'bridge_hash':digest(bridge.read_text(encoding='utf-8'))})
            result=subprocess.run([sys.executable,str(bridge),'--audit-dir',str(root/'audit'),'--profile-manifest',str(manifest),
                '--host-command-json',json.dumps([sys.executable,str(host)])],input=json.dumps(self.packet(),ensure_ascii=False),
                text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertEqual(0,result.returncode,result.stderr)
            self.assertEqual(decode(self.packet(),answer),json.loads(result.stdout))
            self.assertEqual(1,len(list((root/'audit').glob('*.receipt.json'))))

if __name__=='__main__':main=unittest.main()
