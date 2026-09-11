"""Local custody adapter for the existing complete prepared-action state machine."""
from .sdk_prepared_action import PreparedActionAuthority, PreparedActionError

class LocalPreparedActionAuthority(PreparedActionAuthority):
    def _seal(self, claims):
        # A private process-owned lookup handle replaces serialized signed claims.
        return claims['receiptId']

    def _open(self, receipt):
        record = self._records.get(receipt) if isinstance(receipt,str) and len(receipt) <= 4096 else None
        if record is None:
            raise PreparedActionError('PREPARED_ACTION_INVALID', 'Local prepared action is unavailable.')
        return record

    def admit(self, receipt, authorization_token=None):
        with self._lock:
            record = self._open(receipt)
            if record.claims['expiresAt'] <= self._now_ms():
                raise PreparedActionError('PREPARED_ACTION_EXPIRED','Local prepared action expired.')
            if authorization_token is not None:
                raise PreparedActionError('INVALID_REQUEST','Commercial authorization tokens are not accepted by the local host.')
            if record.state != 'prepared':
                raise PreparedActionError('PREPARED_ACTION_INVALID_STATE','Local prepared action state is invalid.')
            self._assert_current_context(record, self._runtime_context())
            record.state = 'authorized'
