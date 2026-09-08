"""Existing SDK inspection operations over a private inherited process pipe."""
import json
import sys
if sys.version_info < (3, 10):
    raise RuntimeError("The standalone native SDK requires Python 3.10 or newer.")
from cutagent_cli.connection import ResolveConnection
from cutagent_cli.adapters import select_adapter
from cutagent_cli.core.sdk_live_inspection import inspect_live_state

MAX_REQUEST_BYTES = 65536

def unavailable(*args, **kwargs):
    raise ValueError("This native inspection dependency has not been composed yet.")

def inspect(request):
    if not isinstance(request, dict) or set(request) - {"operation", "deadlineAtMs", "offset", "pageSize", "search"}:
        raise ValueError("Invalid SDK native inspection request.")
    if request.get("operation") not in {"project.current", "mediaPool.page"}:
        raise ValueError("This existing SDK inspection is not composed yet.")
    connection = ResolveConnection()
    connection.adapter = select_adapter()
    connection.transport = connection.adapter.transport
    connection.resolve = connection.adapter.connect()
    connection.project_manager = connection.resolve.GetProjectManager()
    connection.refresh()
    return inspect_live_state(connection, request["operation"], deadline_at_ms=request.get("deadlineAtMs"),
        list_timelines=unavailable, summarize_timeline=unavailable,
        offset=request.get("offset", 0), page_size=request.get("pageSize", 100), search=request.get("search"))

def main():
    try:
        payload = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1)
        if len(payload) > MAX_REQUEST_BYTES:
            raise ValueError("SDK native inspection request exceeds its size limit.")
        request = json.loads(payload)
        result = inspect(request)
        response = {"ok": True, "data": result}
    except Exception as error:
        response = {"ok": False, "error": {"code": getattr(error, "code", "RUNTIME_UNAVAILABLE"), "message": str(error)}}
    sys.stdout.write(json.dumps(response, separators=(",", ":"), allow_nan=False) + "\n")

if __name__ == '__main__':
    main()
