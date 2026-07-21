"""pytest 公共夹具：让 tests/ 能直接 import app.*（从 backend/ 根运行）。

同时默认阻断真实网络——单元测试一律不允许发起外部调用
（fakeredis 走内存 FakeServer，不经过 socket，不受影响）。
"""

import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    """阻断真实网络；loopback 走真实连接（Windows asyncio 自管道需要）。"""
    real_connect = socket.socket.connect

    def _guarded(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host in ("127.0.0.1", "localhost", "::1"):
            return real_connect(self, address, *args, **kwargs)
        raise RuntimeError(f"unit tests must not call the network: {address}")

    monkeypatch.setattr(socket.socket, "connect", _guarded)

