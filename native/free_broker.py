"""Standalone setup and broker lifecycle for the existing Free Lua spool."""
import argparse
import asyncio
import json
import signal
from cutagent_cli.embedded_bridge import install_script, EmbeddedBridgeServer, EmbeddedBridgeClient, remove_embedded_auth_token

async def serve():
    server=EmbeddedBridgeServer()
    task=asyncio.current_task()
    loop=asyncio.get_running_loop()
    for name in ('SIGINT','SIGTERM'):
        try:loop.add_signal_handler(getattr(signal,name),task.cancel)
        except NotImplementedError:pass
    try:
        await server.start()
    except asyncio.CancelledError:
        pass
    finally:
        remove_embedded_auth_token(server.auth_token,auth_path=server.auth_path)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Local DaVinci Resolve SDK Free transport')
    parser.add_argument('operation',choices=['install','serve','status'])
    args=parser.parse_args()
    if args.operation=='install':print(json.dumps(install_script()))
    elif args.operation=='serve':asyncio.run(serve())
    else:print(json.dumps(EmbeddedBridgeClient().status()))
