"""Readable model-neutral field names; full sources and semantic policy unchanged."""
import argparse,copy,json,subprocess,sys
from pathlib import Path
from portable_screen import load,save,digest,response_schema,load_response

def encode(packet):
    api=copy.deepcopy(packet)
    if 'expected_candidate_ids'not in api:api['output_schema']=response_schema(api['agenda'])
    elif 'output_schema'not in api:raise ValueError('Review task lacks sealed schema')
    return api

def audit_paths(directory,key):
    # Keep the complete content hash in receipts; long Windows workspaces
    # cannot safely use that hash plus descriptive suffixes as filenames.
    short=key[:24]
    return {name:directory/(short+suffix) for name,suffix in {
        'request':'.req.json','stdout':'.out.txt','response':'.res.json',
        'receipt':'.meta.json','failure':'.err.json'}.items()}

def deliver(packet,api,answer,notes,directory,key):
    paths=audit_paths(directory,key)
    save(paths['response'],answer)
    save(paths['receipt'],{'canonical_task_hash':key,'model_packet_hash':digest(api),'response_hash':digest(answer),
        'source_articles_unchanged':api['articles']==packet['articles'],'semantic_policy_unchanged':api['policy']==packet['policy'],
        'parser_notes':notes,'semantic_approval':False})
    return paths

def main():
    p=argparse.ArgumentParser();p.add_argument('--audit-dir',type=Path,required=True)
    p.add_argument('--profile-manifest',type=Path,required=True);p.add_argument('--host-command-json',required=True);a=p.parse_args()
    if digest(Path(__file__).read_text('utf-8'))!=load(a.profile_manifest)['canonical_hash']:raise ValueError('Readable transport changed')
    packet=json.load(sys.stdin);api=encode(packet);key=digest(packet)
    paths=audit_paths(a.audit_dir,key)
    if paths['request'].exists() and load(paths['request'])!=api:raise ValueError('Short audit key collision')
    save(paths['request'],api)
    command=json.loads(a.host_command_json)
    if not isinstance(command,list)or not command or not all(isinstance(x,str)for x in command):raise ValueError('Host must be argv list')
    result=subprocess.run(command,input=json.dumps(api,ensure_ascii=False),text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode:
        save(paths['failure'],{'exit_code':result.returncode,'stage':'native_host'});raise SystemExit(result.returncode)
    try:
        raw=paths['stdout'];raw.write_text(result.stdout,encoding='utf-8');answer,notes=load_response(raw)
        if not isinstance(answer,dict):raise ValueError('Expected object response')
        deliver(packet,api,answer,notes,a.audit_dir,key)
    except (ValueError,OSError) as exc:
        save(paths['failure'],{'exit_code':65,'stage':'canonical_delivery','error_type':type(exc).__name__,'error':str(exc)})
        raise SystemExit(65) from exc
    print(json.dumps(answer,ensure_ascii=False))

if __name__=='__main__':main()
