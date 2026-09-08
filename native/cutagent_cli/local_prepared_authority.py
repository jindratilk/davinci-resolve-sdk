"""Local custody adapter for the existing complete prepared-action state machine."""
import json
from .sdk_prepared_action import PreparedActionAuthority, PreparedActionError, prepared_action_digest

class LocalPreparedActionAuthority(PreparedActionAuthority):
    def _seal(self, claims):
        # A private process-owned lookup handle replaces serialized signed claims.
        return claims['receiptId']

    def _open(self, receipt):
        record = self._records.get(receipt) if isinstance(receipt,str) and len(receipt) <= 4096 else None
        if record is None:
            raise PreparedActionError('PREPARED_ACTION_INVALID', 'Local prepared action is unavailable.')
        return record

    def accept_policy(self, receipt, policy_attestation, policy_decision_digest):
        with self._lock:
            record = self._open(receipt)
            if record.descriptor.operation_class != 'mutation' or record.state != 'prepared':
                raise PreparedActionError('PREPARED_ACTION_INVALID_STATE', 'Local prepared policy state is invalid.')
            if policy_decision_digest != prepared_action_digest('policy-decision', policy_attestation):
                raise PreparedActionError('PREPARED_ACTION_BINDING_MISMATCH', 'Local prepared policy changed.')
            try:
                binding = json.loads(policy_attestation)
            except (ValueError,TypeError) as error:
                raise PreparedActionError('PREPARED_ACTION_INVALID', 'Local prepared policy is invalid.') from error
            expected = {key:record.claims[key] for key in ('accountDigest','impactDigest','executionDigest','projectDigest','timelineDigest','targetsDigest','preStateDigest')}
            expected['receiptDigest'] = prepared_action_digest('receipt',receipt)
            if binding != expected:
                raise PreparedActionError('PREPARED_ACTION_BINDING_MISMATCH', 'Local prepared policy does not match its exact action.')
            record.policy_decision_digest = policy_decision_digest
            record.state = 'policy_accepted'

    def admit(self, receipt, authorization_token=None, policy_decision_digest=None):
        with self._lock:
            record = self._open(receipt)
            if record.claims['expiresAt'] <= self._now_ms():
                raise PreparedActionError('PREPARED_ACTION_EXPIRED','Local prepared action expired.')
            if authorization_token is not None:
                raise PreparedActionError('INVALID_REQUEST','Commercial authorization tokens are not accepted by the local host.')
            if record.descriptor.operation_class == 'mutation':
                if record.state != 'policy_accepted' or policy_decision_digest != record.policy_decision_digest:
                    raise PreparedActionError('EDIT_CONSTRAINT_VIOLATION','Local mutation scope is missing or changed.')
            elif record.state != 'prepared' or policy_decision_digest is not None:
                raise PreparedActionError('PREPARED_ACTION_INVALID_STATE','Local prepared read state is invalid.')
            self._assert_current_context(record, self._runtime_context())
            record.state = 'authorized'
