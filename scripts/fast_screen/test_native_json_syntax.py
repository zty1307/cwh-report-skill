import json,tempfile,unittest
from pathlib import Path
from native_json_syntax import close_completed_root,load_response

class NativeJsonSyntaxContracts(unittest.TestCase):
    def test_only_completed_root_containers_are_appended(self):
        expected={'items':[{'i':'r1','c':'z','g':[]}]};valid=json.dumps(expected,separators=(',',':'))
        for missing in [1,2]:
            raw=valid[:-missing];result,suffix=close_completed_root(raw)
            self.assertEqual(expected,result);self.assertEqual(valid,raw+suffix)
    def test_semantic_and_ambiguous_truncations_are_rejected(self):
        for text in ['{"items":[{"i":"abc','{"items":[{"i":"r1"','{"items":[],','{"items":[{"i":','{"items":[}']:
            with self.subTest(text=text),self.assertRaises(ValueError):close_completed_root(text)
        with self.assertRaises(ValueError):close_completed_root('{"items":[],"items":[]}')
    def test_file_remains_unchanged_and_repair_receipt_is_recorded(self):
        with tempfile.TemporaryDirectory()as d:
            p=Path(d)/'answer.txt';raw='{"items":[{"i":"r1","c":"z","g":[]}'
            p.write_text(raw,encoding='utf-8');value,notes=load_response(p)
            self.assertEqual(raw,p.read_text('utf-8'));self.assertEqual('r1',value['items'][0]['i'])
            self.assertTrue(notes);receipt=json.loads(p.with_suffix('.syntax_repair.json').read_text('utf-8'))
            self.assertFalse(receipt['semantic_values_rewritten']);self.assertFalse(receipt['missing_articles_filled'])

if __name__=='__main__':unittest.main()
