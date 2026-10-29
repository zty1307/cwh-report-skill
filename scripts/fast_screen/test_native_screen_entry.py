import argparse,json,tempfile,unittest
from pathlib import Path
from portable_screen import digest
from native_screen_samples import command_for

class NativeEntryContracts(unittest.TestCase):
    def test_exact_model_and_profile_reach_generic_entry_without_fallback(self):
        with tempfile.TemporaryDirectory()as d:
            here=Path(d);host=here/'adapter.py';host.write_text('pass',encoding='utf-8')
            profile={'glm-5.3-flash-ioa':{'host_script':'adapter.py','host_hash':digest('pass'),'max_batch_chars':30000}}
            a=argparse.Namespace(model='glm-5.3-flash-ioa',out=here/'out',agenda=here/'agenda.json',budget_seconds=480,
                rules=here/'rules.json',compact_profile=here/'compact.json',workbook=here/'完整中文.xlsx',records=None,run=True)
            argv=command_for(a,profile,here)
            self.assertEqual('30000',argv[argv.index('--max-batch-chars')+1]);self.assertIn(str(a.workbook.resolve()),argv)
            host_args=json.loads(argv[argv.index('--host-command-json')+1])
            self.assertEqual(a.model,host_args[host_args.index('--model')+1]);self.assertNotIn('--fallback-model',argv+host_args)
            host.write_text('changed',encoding='utf-8')
            with self.assertRaises(ValueError):command_for(a,profile,here)
            profile[a.model]['host_script']='../other.py'
            with self.assertRaises(ValueError):command_for(a,profile,here)
    def test_unknown_model_is_not_silently_substituted(self):
        with self.assertRaises(ValueError):command_for(argparse.Namespace(model='unknown'),{})
    def test_explicit_glm_generation_and_readable_profile_reach_host(self):
        with tempfile.TemporaryDirectory()as d:
            here=Path(d);host=here/'adapter.py';host.write_text('pass',encoding='utf-8')
            model='glm-5.3-ioa';profile={model:{'host_script':'adapter.py','host_hash':digest('pass'),'max_batch_chars':90000,
                'generation_profile':'glm_low','system_profile':'semantic','output_contract':'canonical','observe_wire':True}}
            a=argparse.Namespace(model=model,out=here/'out',agenda=here/'agenda.json',budget_seconds=480,rules=here/'rules.json',
                compact_profile=here/'transport.json',workbook=None,records=here/'records.json',run=True)
            argv=command_for(a,profile,here);host_argv=json.loads(argv[argv.index('--host-command-json')+1])
            self.assertEqual('canonical',argv[argv.index('--output-contract')+1])
            self.assertEqual('glm_low',host_argv[host_argv.index('--generation-profile')+1])
            self.assertEqual('semantic',host_argv[host_argv.index('--system-profile')+1]);self.assertIn('--observe-wire',host_argv)

if __name__=='__main__':unittest.main()
