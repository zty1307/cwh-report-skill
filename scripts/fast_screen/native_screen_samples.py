"""Simple domestic-model entry; verified transport profiles, no model fallback."""
import argparse,json,subprocess,sys
from pathlib import Path
from portable_screen import load,save,digest

HERE=Path(__file__).resolve().parent

def command_for(a,profiles,here=HERE):
    if a.model not in profiles:raise ValueError('Model has no tested native profile')
    profile=profiles[a.model];name=profile['host_script']
    if not isinstance(name,str)or Path(name).name!=name:raise ValueError('Adapter must be a bundled filename')
    host=here/name
    if digest(host.read_text('utf-8'))!=profile['host_hash']:raise ValueError('Native adapter changed')
    size=profile['max_batch_chars']
    if type(size)is not int or not 2000<=size<=200000:raise ValueError('Invalid full-article batch target')
    out=a.out.resolve()
    host_argv=[sys.executable,str(host),'--model',a.model,'--audit-dir',str(out/'host_audit')]
    host_argv+=['--generation-profile',profile.get('generation_profile','legacy'),'--system-profile',profile.get('system_profile','legacy')]
    if profile.get('observe_wire',False):host_argv.append('--observe-wire')
    argv=[sys.executable,str(here/'screen_samples.py'),'--agenda',str(a.agenda.resolve()),'--out',str(out),
        '--model',a.model,'--budget-seconds',str(a.budget_seconds),'--max-batch-chars',str(size),
        '--rules',str(a.rules.resolve()),'--compact-profile',str(a.compact_profile.resolve()),'--host-command-json',json.dumps(host_argv)]
    argv+=['--output-contract',profile.get('output_contract','compact')]
    argv+=['--max-body-chars',str(profile.get('max_body_chars',450000)),
        '--reading-cost-power',str(profile.get('reading_cost_power',.35)),
        '--exploration-cost-power',str(profile.get('exploration_cost_power',0)),
        '--max-batch-articles',str(profile.get('max_batch_articles',0)),
        '--max-selected-articles',str(profile.get('max_selected_articles',99))]
    argv+=['--workbook',str(a.workbook.resolve())]if a.workbook else['--records',str(a.records.resolve())]
    if a.run:argv.append('--run')
    return argv

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--workbook',type=Path);g.add_argument('--records',type=Path)
    p.add_argument('--agenda',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--model',default='glm-5.3-ioa');p.add_argument('--budget-seconds',type=int,default=360)
    p.add_argument('--rules',type=Path,default=HERE/'collection_frozen_rules.json')
    p.add_argument('--compact-profile',type=Path,default=HERE/'compact_profile_manifest.json');p.add_argument('--run',action='store_true');a=p.parse_args()
    profiles=load(HERE/'native_model_profiles.json');command=command_for(a,profiles)
    if a.out.exists():raise ValueError('Fresh job directory required')
    save(a.out.with_suffix('.native_launch.json'),{'requested_model':a.model,'profile':profiles[a.model],
        'run_requested':a.run,'automatic_model_fallback':False,'formal_ready':False})
    code=subprocess.run(command).returncode
    if code==0 and a.run and(a.out/'results/nominations_pending_review.json').exists():
        from candidate_guards import apply
        apply(a.out.resolve())
    raise SystemExit(code)

if __name__=='__main__':main()
