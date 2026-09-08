"""Same-user local command custody; commercial authorization is not part of this fork."""
import hashlib
import json
import os
import sys


def authorization_required():
    return True


def validate_local_command():
    from .errors import AuthRequired
    expected = os.environ.get('DAVINCI_RESOLVE_SDK_COMMAND_SHA256', '')
    parent = os.environ.get('DAVINCI_RESOLVE_SDK_PARENT_PID', '')
    actual = hashlib.sha256(json.dumps(sys.argv[1:], separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    if parent != str(os.getppid()) or not expected or expected != actual:
        raise AuthRequired('Native commands require exact local SDK process custody.')
    return True


def infer_current_command_id():
    from .main import infer_canonical_command_id
    return infer_canonical_command_id(sys.argv[1:])


def verify_command_authorization(command_id, **kwargs):
    validate_local_command()
    return {'command_id': command_id}


def verify_command_authorization_locally(command_id, **kwargs):
    return verify_command_authorization(command_id, **kwargs)


def is_local_status_probe(args):
    return False


def verify_authorization_token(*args, **kwargs):
    raise PermissionError('Standalone embedded mutation context is not composed yet.')


def _verify_signature(*args, **kwargs):
    raise PermissionError('Standalone prepared-action admission is not composed yet.')


def embedded_command_context(params):
    import time
    import uuid
    from .embedded_bridge import hash_embedded_execute_params
    validate_local_command()
    expected = os.environ.get('DAVINCI_RESOLVE_SDK_COMMAND_SHA256')
    from .policy import _prepared_action_admission, _carrier_issued_admission_is_active
    prepared = _prepared_action_admission.get()
    if prepared is not None:
        if not _carrier_issued_admission_is_active(prepared):
            raise PermissionError('Embedded prepared mutation has no active native carrier custody.')
        command_id = prepared[1]
    else:
        if os.environ.get('CUTAGENT_MUTATION_POLICY_SCOPE_VALID') != '1' or os.environ.get('CUTAGENT_MUTATION_POLICY_ARGS_SHA256') != expected:
            raise PermissionError('Embedded mutation requires a consumed local editing scope.')
        command_id = infer_current_command_id()
    return {'kind':'local_sdk_command_v1', 'args':sys.argv[1:], 'argsDigest':expected,
            'commandId':command_id, 'payloadDigest':hash_embedded_execute_params(params),
            'nonce':uuid.uuid4().hex, 'expiresAtMs':int(time.time()*1000)+30000}


def verify_embedded_command_context(context, params, seen):
    """Called only after the broker's private local capability check succeeds."""
    import time
    from .embedded_bridge import hash_embedded_execute_params
    now = int(time.time()*1000)
    for key, expiry in list(seen.items()):
        if expiry <= now: del seen[key]
    fields = {'kind','args','argsDigest','commandId','payloadDigest','nonce','expiresAtMs'}
    if not isinstance(context,dict) or set(context) != fields or context['kind'] != 'local_sdk_command_v1':
        raise PermissionError('Embedded local command context is invalid.')
    args = context['args']
    if not isinstance(args,list) or not all(isinstance(x,str) for x in args):
        raise PermissionError('Embedded local arguments are invalid.')
    digest = hashlib.sha256(json.dumps(args,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    nonce, expires = context['nonce'], context['expiresAtMs']
    if context['argsDigest'] != digest or context['payloadDigest'] != hash_embedded_execute_params(params):
        raise PermissionError('Embedded local command or native call changed.')
    if not isinstance(context['commandId'],str) or not context['commandId']:
        raise PermissionError('Embedded local command identity is missing.')
    if not isinstance(nonce,str) or len(nonce) != 32 or not all(x in '0123456789abcdef' for x in nonce):
        raise PermissionError('Embedded local nonce is invalid.')
    if type(expires) is not int or not now < expires <= now+30000 or nonce in seen or len(seen) >= 4096:
        raise PermissionError('Embedded local command context expired or was replayed.')
    seen[nonce] = expires
    return context
