import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, copyFile, writeFile, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';

test('full native extraction preserves candidate-owned runtime and renamed Lua launcher', async t => {
  const root = await mkdtemp(join(tmpdir(), 'cutagent-extraction-test-'));
  t.after(() => rm(root, {recursive:true, force:true}));
  const candidate = join(root,'candidate'), source = join(root,'source');
  for (const folder of ['scripts','native/cutagent_cli/assets']) await mkdir(join(candidate,folder),{recursive:true});
  await mkdir(join(source,'cutagent-cli/cutagent_cli/assets'),{recursive:true});
  await mkdir(join(source,'cutagent-cli/cutagent_cli/core'),{recursive:true});
  await writeFile(join(source,'cutagent-cli/cutagent_cli/core/hosted_video.py'),'commercial broker');
  await copyFile(new URL('../scripts/extract-native.py',import.meta.url),join(candidate,'scripts/extract-native.py'));
  await writeFile(join(candidate,'scripts/free-transforms.json'),'{}');
  const entries = [
    {source:'candidate/local.py',destination:'native/local.py',candidateModified:true},
    {source:'cutagent-cli/cutagent_cli/assets/CutAgent.lua',destination:'native/cutagent_cli/assets/CutAgentSDK.lua',candidateModified:true},
  ];
  await writeFile(join(candidate,'native/SOURCE_INVENTORY.json'),JSON.stringify({files:entries}));
  await writeFile(join(candidate,'native/local.py'),'local authority');
  await writeFile(join(candidate,'native/cutagent_cli/assets/CutAgentSDK.lua'),'standalone activation');
  await writeFile(join(source,'cutagent-cli/cutagent_cli/assets/CutAgent.lua'),'commercial activation');
  await writeFile(join(source,'cutagent-cli/cutagent_cli/example.py'),'public owner');
  for (let run=0;run<2;run++) execFileSync('python3',[join(candidate,'scripts/extract-native.py'),source]);
  assert.equal(await readFile(join(candidate,'native/cutagent_cli/assets/CutAgentSDK.lua'),'utf8'),'standalone activation');
  assert.equal(await readFile(join(candidate,'native/local.py'),'utf8'),'local authority');
  assert.equal(await readFile(join(candidate,'native/cutagent_cli/example.py'),'utf8'),'public owner');
  const actual=JSON.parse(await readFile(join(candidate,'native/SOURCE_INVENTORY.json'),'utf8')).files;
  assert.equal(actual.length,3);
  assert.equal(new Set(actual.map(x=>x.destination)).size,3);
});
