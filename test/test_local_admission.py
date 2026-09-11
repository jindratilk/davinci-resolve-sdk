import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'native'))
from cutagent_cli.local_admission import validate_local_command

class LocalAdmissionTests(unittest.TestCase):
    def test_exact_parent_and_argument_custody(self):
        argv = ['cutagent', '-j', 'timeline', 'marker', 'add', '12f']
        digest = hashlib.sha256(json.dumps(argv[1:],separators=(',',':')).encode()).hexdigest()
        env = {'DAVINCI_RESOLVE_SDK_PARENT_PID':str(os.getppid()),'DAVINCI_RESOLVE_SDK_COMMAND_SHA256':digest}
        with patch.object(sys,'argv',argv), patch.dict(os.environ,env,clear=True):
            self.assertTrue(validate_local_command())
            with patch.object(sys,'argv',argv[:-1]+['13f']):
                with self.assertRaises(Exception): validate_local_command()
            with patch.dict(os.environ,{'DAVINCI_RESOLVE_SDK_PARENT_PID':'0'}):
                with self.assertRaises(Exception): validate_local_command()
        with patch.object(sys,'argv',argv), patch.dict(os.environ,{},clear=True):
            with self.assertRaises(Exception): validate_local_command()

    def test_embedded_context_binds_native_payload_and_rejects_replay(self):
        from cutagent_cli.local_admission import embedded_command_context, verify_embedded_command_context
        argv = ['cutagent', '-j', 'timeline', 'marker', 'add', '12f']
        digest = hashlib.sha256(json.dumps(argv[1:],separators=(',',':')).encode()).hexdigest()
        params = {'op':'call','object':'timeline_ref','method':'AddMarker','args':[12,'Blue','Local marker','',1]}
        env = {'DAVINCI_RESOLVE_SDK_PARENT_PID':str(os.getppid()),'DAVINCI_RESOLVE_SDK_COMMAND_SHA256':digest}
        with patch.object(sys,'argv',argv), patch.dict(os.environ,env,clear=True):
            context = embedded_command_context(params)
        seen = {}
        with self.assertRaises(PermissionError): verify_embedded_command_context(context,{**params,'method':'DeleteMarkersByColor'},seen)
        self.assertEqual(seen,{})
        self.assertEqual(verify_embedded_command_context(context,params,seen),context)
        with self.assertRaises(PermissionError): verify_embedded_command_context(context,params,seen)
        with self.assertRaises(PermissionError): verify_embedded_command_context({**context,'expiresAtMs':0},params,{})
