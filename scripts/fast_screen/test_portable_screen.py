import json,tempfile,unittest,sys
from pathlib import Path
import portable_screen as p

AGENDA={'topics':['数字中国建设'],'window_start':'2026-07-10','window_end':'2026-07-13'}
def source(id='r1',text=None):return {'id':id,'title':'解读','content':text or '某大学教授张三表示，算力网的区域供需错配导致资源闲置，跨区域调度需要统一接口标准以减少使用成本。','account':'账号','published_at':'2026-07-11'}
def view(row):
    last=p.segments(row)[-1]['id'];first=p.segments(row)[0]['id']
    return {'topic':'数字中国建设','kind':'person','name':'张三','role':'某大学教授','claim':'算力网的区域供需错配导致资源闲置，跨区域调度需要统一接口标准，以减少企业使用成本并提高算力资源利用效率。',
        'evidence':[first,last],'identity':[first,last],'source_kind':'original','attribution':'explicit','original_date':'','date_evidence':[]}

class PortableTests(unittest.TestCase):
    def test_full_text_preserved_including_whitespace(self):
        r=source(text=('甲。\n\n乙！\n　丙；“丁？”\r\n'*100)+'结尾')
        segs=p.segments(r);self.assertEqual(''.join(s['text']for s in segs),r['content'])
        for s in segs:self.assertEqual(r['content'][s['start']:s['end']],s['text'])
    def test_other_article_range_rejected(self):
        r=source();v=view(r);v['evidence']=['r2:p1','r2:p1'];self.assertTrue(p.format_view(r,v,AGENDA)['errors'])
    def test_single_paragraph_form_normalized_without_ai(self):
        r=source();v=view(r);v['evidence']=v['evidence'][:1];v['identity']=v['identity'][:1]
        result=p.format_view(r,v,AGENDA);self.assertFalse(result['errors']);self.assertEqual(len(result['range_normalizations']),2)
    def test_noncontiguous_paragraph_selection_not_guessed(self):
        r=source(text=('甲'*190+'。')*4);v=view(r);ids=[s['id']for s in p.segments(r)];v['evidence']=[ids[0],ids[2],ids[3]]
        self.assertTrue(p.format_view(r,v,AGENDA)['errors'])
    def test_reversed_range_rejected(self):
        r=source(text=('甲'*190+'。')*3);segs=p.segments(r)
        with self.assertRaises(ValueError):p.resolve_range([segs[-1]['id'],segs[0]['id']],segs)
    def test_generic_role_withheld(self):
        r=source();v=view(r);v['role']='教授';x=p.format_view(r,v,AGENDA)
        self.assertIn('missing_institution',x['errors']);self.assertEqual(x['report_sentence'],'')
    def test_full_person_format_assembled_by_script(self):
        r=source();x=p.format_view(r,view(r),AGENDA);self.assertFalse(x['errors']);self.assertTrue(x['report_sentence'].startswith('某大学教授张三认为，'));self.assertFalse(x['formal_ready'])
    def test_no_truncation_for_small_context(self):
        with tempfile.TemporaryDirectory()as d:
            with self.assertRaises(ValueError):p.prepare([source()],AGENDA,Path(d),10,'test')
    def test_missing_decision_stays_unread(self):
        with tempfile.TemporaryDirectory()as d:
            out=Path(d);p.prepare([source(),source('r2')],AGENDA,out,10000,'test')
            p.save(out/'responses/read-001.json',{'items':[{'id':'r1','code':'news_only','views':[]}]})
            summary=p.ingest(out);self.assertEqual(summary['unread_ids'],['r2']);self.assertEqual(summary['completed_articles'],1)
    def test_duplicate_id_response_quarantined(self):
        with tempfile.TemporaryDirectory()as d:
            out=Path(d);p.prepare([source()],AGENDA,out,10000,'test')
            item={'id':'r1','code':'news_only','views':[]};other={'id':'r1','code':'trading_only','views':[]};p.save(out/'responses/read-001.json',{'items':[item,other]})
            result=p.ingest(out);self.assertEqual(result['completed_articles'],0);self.assertTrue(result['invalid_responses'])
    def test_identical_duplicate_is_removed_without_ai(self):
        with tempfile.TemporaryDirectory()as d:
            out=Path(d);p.prepare([source()],AGENDA,out,10000,'test');item={'id':'r1','code':'news_only','views':[]}
            p.save(out/'responses/read-001.json',{'items':[item,item]});result=p.ingest(out)
            self.assertEqual(result['completed_articles'],1);self.assertFalse(result['invalid_responses']);self.assertTrue(result['parser_notes'])
    def test_one_conflict_preserves_other_articles(self):
        with tempfile.TemporaryDirectory()as d:
            out=Path(d);p.prepare([source(),source('r2')],AGENDA,out,10000,'test')
            p.save(out/'responses/read-001.json',{'items':[{'id':'r1','code':'news_only','views':[]},{'id':'r1','code':'trading_only','views':[]},{'id':'r2','code':'news_only','views':[]}]})
            result=p.ingest(out);self.assertEqual(result['completed_articles'],1);self.assertEqual(result['unread_ids'],['r1'])
    def test_conflict_gets_one_local_completion(self):
        with tempfile.TemporaryDirectory()as d:
            out=Path(d)/'job';host=Path(d)/'fake_host.py'
            host.write_text('import json,sys\np=json.load(sys.stdin)\na=p["articles"]\nr=[{"id":x["id"],"code":"news_only","views":[]}for x in a]\nif len(a)>1:r.append({"id":a[0]["id"],"code":"trading_only","views":[]})\nprint(json.dumps({"items":r}))',encoding='utf-8')
            p.prepare([source(),source('r2')],AGENDA,out,10000,'test');result=p.run(out,[sys.executable,str(host)],10)
            self.assertEqual(result['completed_articles'],2);self.assertFalse(result['unread_ids']);self.assertFalse(result['invalid_responses'])
            self.assertEqual(len(result['resolved_response_issues']),1)
            repair=p.load(next((out/'tasks').glob('repair-*.json')));self.assertEqual([a['id']for a in repair['articles']],['r1'])
    def test_changed_source_refuses_intake(self):
        with tempfile.TemporaryDirectory()as d:
            out=Path(d);p.prepare([source()],AGENDA,out,10000,'test');p.save(out/'sources.json',[source(text='篡改')])
            with self.assertRaises(ValueError):p.ingest(out)
    def test_changed_provider_cannot_reuse_job(self):
        with tempfile.TemporaryDirectory()as d:
            out=Path(d);p.prepare([source()],AGENDA,out,10000,'provider-a')
            with self.assertRaises(ValueError):p.prepare([source()],AGENDA,out,10000,'provider-b')
    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory()as d:
            path=Path(d)/'response.json';path.write_text('{"items":[],"items":[]}',encoding='utf-8')
            with self.assertRaises(ValueError):p.load_response(path)
    def test_single_fence_removed_without_changing_values(self):
        with tempfile.TemporaryDirectory()as d:
            path=Path(d)/'response.json';path.write_text('```json\n{"items":[],"text":"原文\\n保留"}\n```',encoding='utf-8')
            value,notes=p.load_response(path);self.assertEqual(value['text'],'原文\n保留');self.assertTrue(notes)
    def test_truncated_task_source_refused(self):
        with tempfile.TemporaryDirectory()as d:
            out=Path(d);p.prepare([source()],AGENDA,out,10000,'test');task=out/'tasks/read-001.json';packet=p.load(task)
            packet['articles'][0]['paragraphs'][0]['text']='只留局部';p.save(task,packet)
            with self.assertRaises(ValueError):p.ingest(out)
    def test_missing_ids_repaired_without_rereading_completed_article(self):
        with tempfile.TemporaryDirectory()as d:
            out=Path(d)/'job';host=Path(d)/'fake_host.py'
            host.write_text('import json,sys\np=json.load(sys.stdin)\na=p["articles"]\nprint(json.dumps({"items":[{"id":a[0]["id"],"code":"news_only","views":[]}]}))',encoding='utf-8')
            p.prepare([source(),source('r2')],AGENDA,out,10000,'test')
            command=[sys.executable,str(host)]
            result=p.run(out,command,10);self.assertEqual(result['completed_articles'],2)
            tasks=sorted((out/'tasks').glob('repair-*.json'));self.assertEqual(len(tasks),1)
            self.assertEqual([a['id']for a in p.load(tasks[0])['articles']],['r2'])
            calls=len(p.load(out/'runtime.json')['calls']);p.run(out,command,10)
            self.assertEqual(len(p.load(out/'runtime.json')['calls']),calls)
    def test_expired_budget_is_not_reset_on_resume(self):
        with tempfile.TemporaryDirectory()as d:
            out=Path(d);p.prepare([source()],AGENDA,out,10000,'test')
            command=[sys.executable,'-c','raise RuntimeError("must not execute")']
            p.run(out,command,0);deadline=p.load(out/'runtime.json')['deadline']
            result=p.run(out,command,100)
            self.assertEqual(result['unread_ids'],['r1']);self.assertEqual(p.load(out/'runtime.json')['deadline'],deadline)
            self.assertFalse(p.load(out/'runtime.json')['calls'])
if __name__=='__main__':unittest.main()
