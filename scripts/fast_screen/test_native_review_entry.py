import argparse,json,tempfile,unittest
from pathlib import Path
from portable_screen import digest
from native_review_samples import command_for

class NativeReviewEntryContracts(unittest.TestCase):
    def test_explicit_profile_and_fresh_review_contract(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);(root/'host.py').write_text('pass',encoding='utf-8');model='glm-5.3-ioa'
            a=argparse.Namespace(job=root/'job',ids=root/'selected.json',out=root/'review',model=model,
                transport_profile=root/'transport.json',budget_seconds=120)
            profiles={model:{'host_script':'host.py','host_hash':digest('pass'),'generation_profile':'glm_low','system_profile':'semantic'}}
            command=command_for(a,profiles,root)
            self.assertEqual('clarified',command[command.index('--policy-version')+1])
            bridge=json.loads(command[command.index('--command-json')+1]);host=json.loads(bridge[bridge.index('--host-command-json')+1])
            self.assertEqual('glm_low',host[host.index('--generation-profile')+1]);self.assertEqual(model,host[host.index('--model')+1])
            (root/'host.py').write_text('changed',encoding='utf-8')
            with self.assertRaises(ValueError):command_for(a,profiles,root)
    def test_unknown_model_no_silent_fallback(self):
        with self.assertRaises(ValueError):command_for(argparse.Namespace(model='unknown'),{})

if __name__=='__main__':unittest.main()
