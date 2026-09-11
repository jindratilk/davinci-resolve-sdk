"""Extract existing native inspection/transport owners; preserve their behavior."""
from pathlib import Path
import ast,hashlib,json,sys
source=Path(sys.argv[1]).resolve();target=Path(__file__).resolve().parents[1]/'native'
package=source/'cutagent-cli/cutagent_cli'
files=sorted(str(p.relative_to(package)) for p in package.rglob('*')
 if p.is_file() and '__pycache__' not in p.parts
 and (p.suffix in {'.py','.json','.lua','.setting','.xml','.bin'}
      or (p.suffix == '.md' and 'public_reference' in p.parts))
 and p.name not in {'authz.py','authz_jwks.json','hosted_video.py'}
 and 'sdk_inventory' not in p.parts)

selected=set(sys.argv[2:])
existing=json.loads((target/"SOURCE_INVENTORY.json").read_text())["files"] if (target/"SOURCE_INVENTORY.json").exists() else []
entries=[entry for entry in existing if (entry.get("candidateModified") or entry["source"].startswith("candidate/")) or (selected and entry["source"].removeprefix("cutagent-cli/cutagent_cli/") not in selected)]
if selected:
 if not selected.issubset(set(files)): raise ValueError("Unknown native source selection")
 files=[name for name in files if name in selected]
def replace_function(text,name,value):
 tree=ast.parse(text);node=next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
 lines=text.splitlines(keepends=True)
 lines[node.lineno-1:node.end_lineno]=[f'def {name}(*args, **kwargs):\n    return {value}\n']
 return ''.join(lines)

candidate_destinations={entry["destination"] for entry in existing if (entry.get("candidateModified") or entry["source"].startswith("candidate/"))}
for name in files:
 destination_name="assets/CutAgentSDK.lua" if name=="assets/CutAgent.lua" else name
 if "native/cutagent_cli/"+destination_name in candidate_destinations: continue
 src=source/'cutagent-cli/cutagent_cli'/name;raw=src.read_bytes();data=raw
 if name=='sdk_prepared_action.py':
  data=raw.replace(b'context["account"]',b'context["localPrincipal"]').replace(b'context.get("account")',b'context.get("localPrincipal")').replace(b'context["subscription"]',b'None')
 if name=='prepared_action_composition.py':
  data=raw.replace(b'    PreparedActionAuthority,\n',b'').replace(b'from .sdk_prepared_action import (',b'from .local_prepared_authority import LocalPreparedActionAuthority as PreparedActionAuthority\nfrom .sdk_prepared_action import (')
 if name=='prepared_action_host.py':
  data=raw.replace(b'payload["authorizationToken"]',b'payload.get("authorizationToken")')
 if name=='adapters.py':
  data=raw.replace(b'from .authz import authorize_compiled_runtime_import\n\nauthorize_compiled_runtime_import()\n',b'')
 if name=='core/__init__.py':
  data=raw.replace(b'from cutagent_cli.authz import authorize_compiled_runtime_import\n\nauthorize_compiled_runtime_import()\n',b'')
 if name=='embedded_bridge.py':
  data=raw.replace(b'from .authz import authorization_required, infer_current_command_id, verify_authorization_token',b'from .local_admission import authorization_required, infer_current_command_id, verify_authorization_token')
 if name in {'adapters.py','embedded_bridge.py'}:
  data=data.replace(b'Workspace > Scripts > CutAgent.', b'Workspace > Scripts > CutAgentSDK.')
  data=data.replace(b'CUTAGENT_EMBEDDED_',b'DAVINCI_RESOLVE_SDK_EMBEDDED_')
 if name=='embedded_bridge.py':
  text=data.decode().replace('DEFAULT_PORT = 18744','DEFAULT_PORT = 18764').replace('SCRIPT_NAME = "CutAgent.lua"','SCRIPT_NAME = "CutAgentSDK.lua"').replace('/ "CutAgent"','/ "CutAgentSDK"').replace('LEGACY_AUTOSTART_SCRIPT_NAME = "CutAgent.scriptlib"','LEGACY_AUTOSTART_SCRIPT_NAME = "CutAgentSDK.scriptlib"').replace('FOCUS_DEEP_LINK = "cutagent://resolve/free-script"','FOCUS_DEEP_LINK = ""').replace('SPOOL_RESPONSE_KEY = "CutAgentEmbeddedResponse"','SPOOL_RESPONSE_KEY = "CutAgentSdkEmbeddedResponse"')
  for function,value in [('request_cutagent_focus_from_embedded_script','False'),('_desktop_focus_config_from_env','None'),('_request_authorized_command_context','None'),('_authorizer_url','None'),('embedded_auth_scope','"standalone"')]:
   text=replace_function(text,function,value)
  text=text.replace('Workspace > Scripts > CutAgent.', 'Workspace > Scripts > CutAgentSDK.')
  text=replace_function(text,'_command_auth_context','__import__("cutagent_cli.local_admission", fromlist=["embedded_command_context"]).embedded_command_context(args[0] if args else kwargs.get("params", {}))')
  tree=ast.parse(text)
  node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_verify_command_auth')
  lines=text.splitlines(keepends=True)
  lines[node.lineno-1:node.end_lineno]=['    def _verify_command_auth(self, request, params):\n        from .local_admission import verify_embedded_command_context\n        if not hasattr(self, "_local_command_contexts"):\n            self._local_command_contexts = {}\n        return verify_embedded_command_context(request.get("command_auth"), params, self._local_command_contexts)\n']
  text=''.join(lines)
  data=text.encode()
 if name=='assets/CutAgent.lua':
  data=data.replace(b'__CUTAGENT_BRIDGE_RUNNING',b'__CUTAGENT_SDK_BRIDGE_RUNNING').replace(b'CutAgent.lua',b'CutAgentSDK.lua').replace(b'[CutAgent]',b'[CutAgent SDK]').replace(b'Workspace > Scripts > CutAgent',b'Workspace > Scripts > CutAgentSDK').replace(b'CutAgent.log',b'CutAgentSDK.log').replace(b'"CutAgent"',b'"CutAgentSDK"').replace(b'local FOCUS_DEEP_LINK = "cutagent://resolve/free-script"',b'local FOCUS_DEEP_LINK = ""').replace(b'\nrequest_cutagent_focus_via_broker()\n',b'\n-- Standalone runtime does not focus a commercial desktop application.\n')
 for change in json.loads((target.parent/'scripts/free-transforms.json').read_text()).get('cutagent-cli/cutagent_cli/'+name,[]):
  before=change['before'].encode();after=change['after'].encode()
  if after in data: continue
  if data.count(before) != 1: raise ValueError('Accepted Free source context drift: '+name)
  data=data.replace(before,after,1)
 destination_name='assets/CutAgentSDK.lua'  if name=='assets/CutAgent.lua' else name
 dst=target/'cutagent_cli'/destination_name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(data)
 entries.append({'source':'cutagent-cli/cutagent_cli/'+name,'destination':'native/cutagent_cli/'+destination_name,'sourceSha256':hashlib.sha256(raw).hexdigest(),'sha256':hashlib.sha256(data).hexdigest(),'transformed':data!=raw})
test_source=source/'cutagent-cli/tests/test_project_preset_export_prepared_action.py'
test_destination=target.parent/'test/test_project_preset_export_prepared_action.py'
if not selected and test_source.is_file():
 raw=test_source.read_bytes()
 data=raw.replace(b'        "mutationPolicy": {"scopeId": "scope-project", "scopeRevision": 1},\n', b'')
 test_destination.write_bytes(data)
(target/'SOURCE_INVENTORY.json').write_text(json.dumps({'files':entries},indent=2)+'\n')
print(f'Extracted {len(entries)} native inspection/transport inputs; no commercial authorization implementation')
