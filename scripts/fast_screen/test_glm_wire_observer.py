import json,os,subprocess,tempfile,unittest
from pathlib import Path

NODE=Path(r'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
OBSERVER=Path(__file__).with_name('glm_wire_observer.cjs')

class ReadOnlyWireObservation(unittest.TestCase):
    @unittest.skipUnless(NODE.is_file(),'Native Node runtime unavailable')
    def test_observer_does_not_change_payload_or_log_text_credentials(self):
        with tempfile.TemporaryDirectory()as d:
            output=Path(d)/'scalars.jsonl'
            packet={'model':'glm-5.3-flash-ioa','messages':[{'role':'user','content':'私有原文不应出现在标量日志中'}],
                    'reasoning_effort':'low','thinking':{'type':'enabled'},'authorization':'test_secret_not_logged'}
            code='const p=JSON.parse(process.argv[1]);process.stdout.write(JSON.stringify(p));'
            result=subprocess.run([str(NODE),'--require',str(OBSERVER),'-e',code,json.dumps(packet,ensure_ascii=False)],
                                  env={**os.environ,'CWH_GLM_WIRE_OBSERVER_FILE':str(output)},capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(0,result.returncode);self.assertEqual(packet,json.loads(result.stdout))
            raw=output.read_text('utf-8');row=json.loads(raw)
            self.assertEqual('low',row['reasoning_effort']);self.assertEqual('enabled',row['thinking.type'])
            self.assertNotIn(packet['authorization'],raw);self.assertNotIn(packet['messages'][0]['content'],raw)
            self.assertEqual(64,len(row['messages_sha256']))
    @unittest.skipUnless(NODE.is_file(),'Native Node runtime unavailable')
    def test_other_models_are_not_observed(self):
        with tempfile.TemporaryDirectory()as d:
            output=Path(d)/'scalars.jsonl';packet={'model':'unrelated_model','messages':[]}
            code='process.stdout.write(JSON.stringify(JSON.parse(process.argv[1])));'
            result=subprocess.run([str(NODE),'--require',str(OBSERVER),'-e',code,json.dumps(packet)],
                                  env={**os.environ,'CWH_GLM_WIRE_OBSERVER_FILE':str(output)},capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(packet,json.loads(result.stdout));self.assertFalse(output.exists())

if __name__=='__main__':unittest.main()
