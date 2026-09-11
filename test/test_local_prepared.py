from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'native'))
from local_prepared_fixture import authority_env
from cutagent_cli.sdk_prepared_action import PreparedActionError

class LocalPreparedTests(unittest.TestCase):
    def admit(self, env, prepared):
        env['authority'].admit(prepared['receipt'])

    def test_existing_execution_verification_and_one_use_without_commercial_tokens(self):
        env=authority_env(); owner=env['authority']
        prepared=owner.prepare(env['request'])
        self.assertTrue(prepared['receipt'].startswith('prepared_'))
        self.assertNotIn('.',prepared['receipt'])
        with self.assertRaises(PreparedActionError): owner.admit(prepared['receipt'],authorization_token='unaccepted-token')
        self.admit(env,prepared)
        with self.assertRaises(PreparedActionError): owner.admit(prepared['receipt'])
        terminal=owner.execute(prepared['receipt'])
        self.assertEqual(terminal['status'],'succeeded')
        self.assertEqual(env['descriptor'].executions,1)
        with self.assertRaises(PreparedActionError): owner.execute(prepared['receipt'])
        self.assertEqual(env['descriptor'].executions,1)
        self.assertTrue(env['terminals'])

    def test_target_change_still_fails_before_native_handler(self):
        env=authority_env(); owner=env['authority']; prepared=owner.prepare(env['request'])
        self.admit(env,prepared)
        env['descriptor'].targets=[{**env['descriptor'].targets[0],'revision':'changed'}]
        terminal=owner.execute(prepared['receipt'])
        self.assertNotEqual(terminal['status'],'succeeded')
        self.assertEqual(env['descriptor'].executions,0)

    def test_local_identity_change_and_foreign_receipt_are_rejected(self):
        env=authority_env(); owner=env['authority']; prepared=owner.prepare(env['request'])
        with self.assertRaises(PreparedActionError): owner.admit('prepared_foreign')
        env['context']['localPrincipal']={'fingerprint':'changed-owner'}
        with self.assertRaises(PreparedActionError): self.admit(env,prepared)
        self.assertEqual(env['descriptor'].executions,0)
