"""Reproducible selected-source extraction. Run only against the authorized source tree."""
import hashlib,json,re,shutil,sys
from pathlib import Path
from prepared_transforms import transform as transform_prepared
source=Path(sys.argv[1]).resolve(); target=Path(__file__).resolve().parents[1]
inventory=[]
selected=set(sys.argv[2:])
existing={entry["source"]:entry for entry in json.loads((target/"EXTRACTION_INVENTORY.json").read_text())["files"]} if selected else {}
if selected and not selected.issubset(existing): raise ValueError("Unknown existing source selection")
def apply_free_transform(path,text):
    for change in json.loads((target/'scripts/free-transforms.json').read_text()).get(path,[]):
        if change['after'] in text: continue
        if text.count(change['before']) != 1: raise ValueError('Accepted Free source context drift: '+path)
        text=text.replace(change['before'],change['after'],1)
    return text

def transform(path,text):
    text=apply_free_transform(path,text)
    if path in {'sdk/README.md','sdk/LIFECYCLE.md'}:
        return (target/'docs/package'/Path(path).name).read_text()
    # The fork has a distinct distribution; retain every public method and wire operation.
    text=text.replace('desktop_managed','standalone_local').replace('@cutagent/sdk','davinci-resolve-sdk')
    if path.startswith('bridge/'):
        text=text.replace('"./cutagent-cli-runtime.js"', '"../../local/cli-runtime.mjs"')
        text=text.replace('"../providers/resource-loader.js"', '"../../local/resources.mjs"')
    if path=='bridge/services/cutagent-cli-authorization.js':
        text=text.replace('import { createDesktopBridgeCapability } from "../app/desktop-bridge-secret.js";', 'import {createLocalCapability as createDesktopBridgeCapability} from "../../local/capability.mjs";')
    if path=='bridge/services/sdk-render-action-service.js':
        text=text.replace('"./attachment-content-service.js"','"../../local/native-tools.mjs"')
    if path=='bridge/services/sdk-caption-actions.js':
        text=text.replace('authService?.captureDesktopAuthBrokerSession','authService?.capture').replace('authService?.assertSessionIdentityCurrent','authService?.assertCurrent')
    if path=='bridge/services/resolve-service.js':
        text=text.replace('CUTAGENT_EMBEDDED_', 'DAVINCI_RESOLVE_SDK_EMBEDDED_').replace('18744','18764').replace('18745','18765').replace('18746','18766').replace('18747','18767').replace('18748','18768').replace('18749','18769')
        text=text.replace('"CutAgent", scopedFileName','"DaVinciResolveSDK", scopedFileName')
        start=text.index('function getEmbeddedAuthScope(')
        end=text.index('\nfunction ',start+1)
        text=text[:start]+'function getEmbeddedAuthScope() { return "standalone"; }\n'+text[end:]
        text=text.replace('    readSdkLiveInspection,','    executeLocalSdkCommand: (args, options) => parseJson(args, getTimeoutMs(), options),\n    readSdkLiveInspection,')
        text=text.replace('env: buildCutAgentCliEnv({', 'env: buildCutAgentCliEnv({args: jsonArgs,')
    if path=='bridge/services/version-checkpoint-service.js':
        text=text.replace('env: buildCutAgentCliEnv({', 'env: buildCutAgentCliEnv({args: jsonArgs,')
    if path=='bridge/services/sdk-runtime-service.js':
        text=text.replace('./cutagent-cli-runtime.js','../../local/native-identity.mjs')
    if path=='bridge/app/sdk-runtime-route.js':
        start=text.index('async function refreshAndRequireSubscription(')
        end=text.index('\nexport function getSdkRuntimeRoutePaths',start)
        text=text[:start]+'''async function requireLocalPrincipal(authService) {
  const authenticated = await captureAuthenticatedSdkRequest(authService);
  assertAuthenticatedSdkRequestCurrent(authService, authenticated);
  return authenticated;
}
'''+text[end:]
        text=text.replace('refreshAndRequireSubscription(authService, desktopAuthBroker)','requireLocalPrincipal(authService)')
        text=text.replace('import { SDK_VOICE_CATALOG_ACTIVATED } from "../services/sdk-voice-action-service.js";', 'const SDK_VOICE_CATALOG_ACTIVATED = false;')
    if path=='bridge/services/sdk-authenticated-request.js':
        text='''export async function captureAuthenticatedSdkRequest(authority) {
  if (typeof authority?.capture !== "function") throw Object.assign(new Error("Local principal authority is unavailable."), {code:"AUTHENTICATION_REQUIRED"});
  return authority.capture();
}
export function assertAuthenticatedSdkRequestCurrent(authority, authenticated) {
  authority.assertCurrent(authenticated);
}
'''
    if path=='bridge/app/desktop-bridge-secret.js':
        text='export {requireLocalCapability as requireDesktopBridgeSecret} from "../../local/capability.mjs";\n'
    return transform_prepared(path,text)

def copy(path,dest):
    if selected and path not in selected:
        inventory.append(existing[path])
        return dest.read_text() if dest.suffix in {".js",".mjs",".ts",".json",".md"} else ""
    raw=(source/path).read_bytes()
    text=raw.decode() if Path(path).suffix in {'.js','.mjs','.ts','.json','.md'} else None
    data=transform(path,text).encode() if text is not None else raw
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    inventory.append({'source':path,'destination':str(dest.relative_to(target)),'sourceSha256':hashlib.sha256(raw).hexdigest(),'sha256':hashlib.sha256(data).hexdigest(),'transformed':raw!=data})
    return data.decode() if text is not None else ''

for path in sorted((source/'sdk/src').rglob('*')):
    if path.is_file(): copy(str(path.relative_to(source)),target/'sdk'/path.relative_to(source/'sdk'))
for name in ['LICENSE','README.md','LIFECYCLE.md','compatibility.json','compatibility.schema.json','tsconfig.json','tsconfig.types.json','scripts/build-js.mjs']:
    copy('sdk/'+name,target/'sdk'/name)
# Resolve only the imported closure of existing full SDK route/session owners.
queue=['bridge/app/sdk-runtime-route.js','bridge/services/sdk-runtime-service.js',
       'bridge/repos/sdk-operation-repo.js','bridge/services/sdk-operation-authority.js',
       'bridge/repos/constraint-scope-repo.js','bridge/services/sdk-direct-mutation-policy-authority.js',
       'bridge/services/resolve-service.js','bridge/services/cutagent-cli-authorization.js',
       *['bridge/services/'+name+'.js' for name in [
          'sdk-marker-action-service','sdk-timeline-item-move-service','sdk-timeline-blade-service',
          'sdk-timeline-structure-action-service','sdk-color-action-service','sdk-timeline-edit-action-service',
          'sdk-multicam-action-service','sdk-project-media-action-service','sdk-storage-action-service',
          'sdk-inventory-action-service','sdk-artifact-service','sdk-low-level-action-service','sdk-action-registry','color-asset-service','sdk-render-action-service','sdk-caption-actions','sdk-fusion-graph-action','sdk-prepared-action-production-composition','sdk-professional-av-prepared-action-builders','sdk-fusion-timeline-prepared-action-contributions','sdk-color-prepared-action-contributions','sdk-editorial-project-prepared-action-contributions','sdk-audio-operations-prepared-action-contributions','sdk-fairlight-prepared-action-builders','sdk-project-render-storage-media-prepared-action-builders','sdk-project-library-destination-service','sdk-workflow-authority','version-checkpoint-service']]]
seen=set()
while queue:
    path=queue.pop()
    if path in seen: continue
    seen.add(path)
    if not (source/path).is_file(): raise ValueError('Missing source import '+path)
    text=copy(path,target/'runtime'/path)
    for dep in re.findall(r'(?:from\s+|import\s*\(\s*|import\s*)[\"\']([^\"\']+)[\"\']',text):
        if not dep.startswith('.') or '/local/' in dep: continue
        resolved=(Path(path).parent/dep)
        normalized=str((source/resolved).resolve().relative_to(source))
        if normalized not in seen: queue.append(normalized)
(target/'EXTRACTION_INVENTORY.json').write_text(json.dumps({'kind':'selected-sdk-route-source-closure','files':inventory},indent=2)+'\n')
print(f'Extracted {len(inventory)} selected files ({len(seen)} runtime dependencies)')
