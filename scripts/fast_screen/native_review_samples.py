"""Simple fresh-context native review entry; no hand-built host argv required."""
import argparse,json,subprocess,sys
from pathlib import Path
from portable_screen import load,digest

HERE=Path(__file__).resolve().parent

def command_for(a,profiles,here=HERE):
    if a.model not in profiles:raise ValueError('Model has no configured native profile')
    profile=profiles[a.model];name=profile['host_script']
    if Path(name).name!=name:raise ValueError('Host must be bundled filename')
    host=here/name
    if digest(host.read_text('utf-8'))!=profile['host_hash']:raise ValueError('Native adapter changed')
    out=a.out.resolve()
    host_argv=[sys.executable,str(host),'--model',a.model,'--generation-profile',profile.get('generation_profile','legacy'),
        '--system-profile',profile.get('system_profile','legacy'),'--audit-dir',str(out/'host_audit')]
    if profile.get('observe_wire',False):host_argv.append('--observe-wire')
    bridge=[sys.executable,str(here/'canonical_screen_transport.py'),'--audit-dir',str(out/'transport_audit'),
        '--profile-manifest',str(a.transport_profile.resolve()),'--host-command-json',json.dumps(host_argv)]
    return[sys.executable,str(here/'review_selected_candidates.py'),'--queue',str(a.job.resolve()/'review_queue'),
        '--ids',str(a.ids.resolve()),'--out',str(out),'--policy-version','clarified',
        '--command-json',json.dumps(bridge),'--budget-seconds',str(a.budget_seconds)]

def main():
    p=argparse.ArgumentParser();p.add_argument('--job',type=Path,required=True);p.add_argument('--ids',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--model',default='glm-5.3-ioa')
    p.add_argument('--budget-seconds',type=int,default=120)
    p.add_argument('--transport-profile',type=Path,default=HERE/'compact_profile_manifest.json');a=p.parse_args()
    if a.out.exists():raise ValueError('Fresh independent review directory required')
    command=command_for(a,load(HERE/'native_model_profiles.json'))
    raise SystemExit(subprocess.run(command).returncode)

if __name__=='__main__':main()
