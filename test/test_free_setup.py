import asyncio
import base64
import json
import threading
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'native'))
from cutagent_cli import embedded_bridge as bridge

class FreeSetupTests(unittest.TestCase):
    def test_fusion_settings_read_does_not_admit_clipboard_copy(self):
        server = bridge.EmbeddedBridgeServer(port=0, auth_token='local-test-token', publish_auth=False)
        self.assertIsNone(server._validate_execute_request({
            'id': 'fusion-settings-inspect',
            'params': {'op': 'call', 'target': 'fusion_comp', 'method': 'CopySettings', 'args': [{}]},
        }))
        self.assertIn('CopySettings', bridge.READ_ONLY_RESOLVE_METHODS)
        self.assertNotIn('CopySettings', bridge.MUTATING_RESOLVE_METHODS)
        self.assertNotIn('Copy', bridge.READ_ONLY_RESOLVE_METHODS)

    def test_setup_uses_separate_script_state_and_no_commercial_focus(self):
        with tempfile.TemporaryDirectory() as root:
            home=Path(root)
            original=bridge.utility_scripts_dir(home).parent/'CutAgent.scriptlib'
            original.parent.mkdir(parents=True); original.write_text('original app file')
            with patch.dict(os.environ,{'DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_PATH':str(home/'state'/'auth.json')}):
                result=bridge.install_script(home)
            script=Path(result['path'])
            self.assertEqual(script.name,'CutAgentSDK.lua')
            self.assertEqual(original.read_text(),'original app file')
            self.assertNotRegex(script.read_text(),r'__[A-Z][A-Z0-9_]+__')
            self.assertNotIn('__CUTAGENT_BRIDGE_RUNNING',script.read_text())
            self.assertIn('local FOCUS_DEEP_LINK = ""',script.read_text())
            self.assertIn('CutAgentSDK',str(bridge.embedded_auth_path(home)))
            self.assertFalse(bridge.request_cutagent_focus_from_embedded_script())
            self.assertIsNone(bridge._desktop_focus_config_from_env())

    def test_independent_broker_authentication_and_bounded_shutdown(self):
        with tempfile.TemporaryDirectory() as root:
            auth_path=Path(root)/'auth.json'
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
            env={**os.environ,'DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_PATH':str(auth_path),'DAVINCI_RESOLVE_SDK_EMBEDDED_PORT':str(port)}
            process=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/'native/free_broker.py'),'serve'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                limit=time.monotonic()+5
                while not auth_path.exists() and process.poll() is None and time.monotonic()<limit:time.sleep(.025)
                self.assertTrue(auth_path.is_file())
                with patch.dict(os.environ,env):
                    client=bridge.EmbeddedBridgeClient()
                    status=client.status()
                    self.assertTrue(status['running'])
                    self.assertFalse(status['connected'])
                    rejected=bridge.EmbeddedBridgeClient(host='127.0.0.1',port=port,auth_token='wrong-token').status()
                    self.assertEqual(rejected['error_code'],'EMBEDDED_BRIDGE_AUTH_FAILED')
                self.assertEqual(auth_path.stat().st_mode&0o777,0o600)
                self.assertEqual(bridge.embedded_spool_paths(auth_path=auth_path)['root'].stat().st_mode&0o777,0o700)
            finally:
                process.terminate()
                try:process.communicate(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.communicate(timeout=3);self.fail('Broker failed bounded shutdown')
            self.assertFalse(auth_path.exists())

    def test_spool_acknowledgement_removes_request_before_execution(self):
        with tempfile.TemporaryDirectory() as root:
            server=bridge.EmbeddedBridgeServer(auth_path=Path(root)/'auth.json',auth_token='local-test-token',publish_auth=False)
            server.spool_paths['root'].mkdir(mode=0o700)
            observed=[]
            def lua_peer():
                request_path=server.spool_paths['request']
                limit=time.monotonic()+2
                while not request_path.exists() and time.monotonic()<limit:time.sleep(.01)
                request=json.loads(base64.b64decode(request_path.read_text().removeprefix('return "').removesuffix('"\n')))
                accepted={'id':request['id'],'state':'accepted','auth_token':'local-test-token','client':{'role':'lua','connection':'file_spool'}}
                def respond(value):
                    encoded=base64.b64encode(json.dumps(value).encode()).decode()
                    server.spool_paths['response'].write_text(f'GlobalData = {{ {bridge.SPOOL_RESPONSE_KEY} = "{encoded}" }}\n')
                respond(accepted)
                limit=time.monotonic()+2
                while request_path.exists() and time.monotonic()<limit:time.sleep(.01)
                observed.append(not request_path.exists())
                respond({**accepted,'state':'complete','result':{'version_string':'21.1.0.14'}})
            peer=threading.Thread(target=lua_peer)
            peer.start()
            try:
                result=asyncio.run(server._spool_round_trip({'method':'execute','params':{'op':'get_version'}},accept_timeout=1,response_timeout=2))
            finally:
                peer.join(timeout=3)
            self.assertFalse(peer.is_alive())
            self.assertEqual(observed,[True])
            self.assertEqual(result['result']['version_string'],'21.1.0.14')
            self.assertEqual(server.spool_paths['response'].stat().st_mode&0o777,0o600)

    def test_stale_spool_response_does_not_keep_connection_alive(self):
        with tempfile.TemporaryDirectory() as root:
            server=bridge.EmbeddedBridgeServer(auth_path=Path(root)/'auth.json',auth_token='local-test-token',publish_auth=False)
            payload={'id':'old','auth_token':'local-test-token','updated_at':time.time()-60,'client':{'role':'lua','connection':'file_spool'}}
            self.assertTrue(server._record_spool_response(payload))
            self.assertFalse(server._spool_connected())

if __name__=='__main__':unittest.main()
