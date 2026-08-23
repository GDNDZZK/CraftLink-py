import asyncio
import json

import websockets

from core import ModManager, data
from crypto import decrypt, derive_key
from logger import Logger

HANDSHAKE_TIMEOUT = 10
PING_INTERVAL = 10
PONG_TIMEOUT = 2


class Connection:
    def __init__(self, server, ws, host, key):
        self.server = server
        self.ws = ws
        self.host = host
        self.key = key
        self.log = server.log
        self.pong = asyncio.Event()

    async def recv_loop(self):
        try:
            async for raw in self.ws:
                await self._handle(raw)
        except websockets.ConnectionClosed:
            pass

    async def ping_loop(self):
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL)
                self.pong.clear()
                await self.ws.send(json.dumps({"t": "ping"}))
                try:
                    await asyncio.wait_for(self.pong.wait(), PONG_TIMEOUT)
                except asyncio.TimeoutError:
                    self.log.warn("连接超时")
                    await self.ws.close()
                    return
        except websockets.ConnectionClosed:
            pass

    async def _handle(self, raw):
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(msg, dict):
            return
        t = msg.get("t")
        if t == "pong":
            self.pong.set()
            return
        if t == "ping":
            await self.ws.send(json.dumps({"t": "pong"}))
            return
        enc = msg.get("d")
        if enc is None:
            return
        try:
            inner = json.loads(decrypt(self.key, enc))
        except Exception as e:
            self.log.warn(f"{self.host} 数据解密失败: {e}")
            return
        if not isinstance(inner, dict):
            return
        self.server.mods.dispatch(data(inner.get("t"), inner.get("d")))


class CraftLinkServer:
    def __init__(self, host: str, port: int, mods: ModManager):
        self.host = host
        self.port = port
        self.mods = mods
        self.log = Logger()

    async def serve_forever(self):
        async with websockets.serve(self._handler, self.host, self.port):
            self.log.info(f"服务器已启动 ws://{self.host}:{self.port}")
            await asyncio.Future()

    async def _handler(self, ws, path=None):
        host = ws.remote_address[0] if ws.remote_address else "unknown"
        try:
            raw = await asyncio.wait_for(ws.recv(), HANDSHAKE_TIMEOUT)
            hs = json.loads(raw)
        except Exception:
            hs = {}
        if not isinstance(hs, dict):
            hs = {}
        gdndzzk = hs.get("GDNDZZK")
        version = hs.get("version")
        token = hs.get("token")
        if not isinstance(gdndzzk, str) or not isinstance(version, str) or not isinstance(token, str):
            self.log.warn(f"握手失败,协议不匹配,请求来自{host}")
            await ws.close()
            return
        if "CraftLink" not in gdndzzk:
            self.log.warn(f"握手失败,协议不匹配,错误的协议:{gdndzzk},请求来自{host}")
            await ws.close()
            return
        if version != "api_v1":
            self.log.warn(f"握手失败,版本不匹配,请求来自{host}")
            await ws.close()
            return
        self.log.info(f"{host} 握手成功 ua={hs.get('ua')}")
        conn = Connection(self, ws, host, derive_key(token))
        recv_task = asyncio.create_task(conn.recv_loop())
        ping_task = asyncio.create_task(conn.ping_loop())
        done, pending = await asyncio.wait({recv_task, ping_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await ws.close()
        self.log.info(f"{host} 连接断开")
