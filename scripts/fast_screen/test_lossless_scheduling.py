import copy,json,sys,tempfile,unittest
from pathlib import Path
from conservative_filter import compact,sentence_records,_ALNUM_LOWER
from portable_screen import prepare,load,save,run,digest

class LosslessScheduling(unittest.TestCase):
    def test_normalization_matches_legacy_for_every_unicode_codepoint(self):
        value=''.join(map(chr,range(0x110000)))
        expected=''.join(c.lower() for c in value if c.isalnum())
        self.assertEqual(compact(value),expected)
        self.assertEqual(compact('ΟΣ İ_ＡＢＣ１２３。'),'οσi\u0307ａｂｃ１２３')
        _ALNUM_LOWER.clear()

    def test_sentence_rows_preserve_original_split_and_normalization(self):
        import re
        value='\n  第一段，ＡＢＣ  。\nΟΣ İ _ 42！ ; 空\t格？\n'
        expected=[(p.strip(),''.join(c.lower() for c in p if c.isalnum()))
            for p in re.split(r'[。！？!?；;\n]+',value) if any(c.isalnum() for c in p)]
        self.assertEqual(sentence_records(value),expected)

    def test_balanced_packets_preserve_every_full_article_once(self):
        records=[{'id':f'r{i}','title':f'原题{i}','account':'原账号','content':('完整原文。'*n)+f'末尾{i}。'}
            for i,n in enumerate([1800,15,800,20,700,25,600,30,500,35],1)]
        agenda={'topics':['议题'],'topic_aliases':[['议题']]};before=copy.deepcopy(records)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);prepare(records,agenda,root,20000,'test',mode='recall_v8',max_articles_per_batch=3,batch_strategy='balanced')
            batches=[load(p) for p in sorted((root/'tasks').glob('read-*.json'))]
            restored={a['id']:''.join(p['text'] for p in a['paragraphs']) for b in batches for a in b['articles']}
            self.assertEqual(sum(len(b['articles']) for b in batches),len(records))
            self.assertEqual(restored,{r['id']:r['content'] for r in records});self.assertEqual(records,before)
            sizes=[sum(len(json.dumps(a,ensure_ascii=False)) for a in b['articles']) for b in batches]
            self.assertEqual(sizes,sorted(sizes));self.assertTrue(all(n<=20000 for n in sizes))
            self.assertTrue(all(len(b['articles'])<=3 for b in batches))
            self.assertEqual(load(root/'manifest.json')['sources_hash'],digest(records))

    def test_timed_out_batch_stays_unread_and_next_original_batch_can_complete(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);records=[{'id':f'r{i}','title':'原题','content':'完整原文。'*40} for i in [1,2]]
            prepare(records,{'topics':['题'],'topic_aliases':[['题']]},root,20000,'test',mode='recall_v8',max_articles_per_batch=1,batch_strategy='balanced')
            manifest=load(root/'manifest.json');manifest['request_policy']['max_request_seconds']=1;save(root/'manifest.json',manifest)
            host=root/'fake_host.py';host.write_text('import json,sys,time\np=json.load(sys.stdin)\n'
                'if p["expected_article_ids"]==["r1"]:time.sleep(3)\n'
                'print(json.dumps({"items":[{"id":i,"code":"news_only","views":[]} for i in p["expected_article_ids"]]}))','utf-8')
            got=run(root,[sys.executable,str(host)],6)
            self.assertEqual(got['completed_articles'],1);self.assertEqual(got['unread_ids'],['r1'])
            calls=load(root/'runtime.json')['calls'];self.assertEqual([c['exit_code'] for c in calls],[124,0])
            self.assertEqual([c['task'] for c in calls],['read-001.json','read-002.json'])

if __name__=='__main__':unittest.main()
