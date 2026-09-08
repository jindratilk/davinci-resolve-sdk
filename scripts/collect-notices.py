"""Collect dependency license texts from this candidate's installed locked environment."""
from pathlib import Path
import hashlib, importlib.metadata as metadata, json, shutil
root=Path(__file__).resolve().parents[1]
out=root/'THIRD_PARTY_NOTICES'
if out.exists(): shutil.rmtree(out)
out.mkdir(exist_ok=True)
entries=[]
def record(ecosystem,name,version,license_value,base,files):
    dest=out/ecosystem/(name.replace('/','__')+'-'+version)
    dest.mkdir(parents=True,exist_ok=True)
    notices=[]
    for source in sorted(set(files)):
        if not source.is_file() or source.is_symlink():continue
        rel=source.relative_to(base)
        target=dest/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        notices.append({'path':str(target.relative_to(root)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    entries.append({'ecosystem':ecosystem,'name':name,'version':version,'declaredLicense':license_value,'notices':notices})
lock=json.loads((root/'package-lock.json').read_text())
for location, locked in sorted(lock['packages'].items()):
    if 'node_modules/' not in location or locked.get('link'):continue
    package=root/location/'package.json'
    if not package.is_file():continue
    if package.parent.is_symlink():continue
    try:d=json.loads(package.read_text())
    except (ValueError,OSError):continue
    if not d.get('name') or not d.get('version'):continue
    base=package.parent
    files=[f for f in base.iterdir() if f.is_file() and f.name.lower().split('.')[0] in ('license','licence','notice','copying','copyright')]
    record('npm',d['name'],d['version'],d.get('license'),base,files)
for dist in metadata.distributions():
    name=dist.metadata.get('Name','')
    if name.lower() in {'pip','setuptools'}:continue
    base=Path(dist.locate_file(''))
    files=[]
    for f in dist.files or []:
        if any(p.lower() in ('licenses','license','licence','notice','copying') or p.lower().startswith(('license.','licence.','notice.','copying.')) for p in f.parts):files.append(Path(dist.locate_file(f)))
    record('python',name,dist.version,dist.metadata.get('License-Expression') or dist.metadata.get('License'),base,files)
(out/'inventory.json').write_text(json.dumps(entries,indent=2)+'\n')
missing=[f"{e['ecosystem']}:{e['name']}@{e['version']}" for e in entries if not e['notices']]
(out/'README.md').write_text('# Third-party dependency notices\n\nCollected from installed locked npm (including development/build dependencies) and Python dependencies. Each preserved text is identified by package/version and SHA256 in inventory.json. DaVinci Resolve, Node.js, Python, FFmpeg and external LuaSocket binaries are not redistributed. Their installation licenses apply separately.\n\nPackages without an installed standalone license/notice file require review before bundling:\n\n'+''.join('- '+m+'\n' for m in missing))
print(json.dumps({'packages':len(entries),'missingStandaloneNotice':missing}))
