"""
TravelMind Agent — WebBridge CLI 封装

CLI+Skill 模式：浏览器自动化一律走这里，不要手写 curl。
临时 JSON 文件 + curl.exe（Windows 下 shell 内联中文会编码损坏）。
零 LLM 成本——所有调用只经过本机 WebBridge daemon (127.0.0.1:10086)。

用法:
    from scripts.wb import navigate, evaluate, snapshot, close_session
    navigate("http://localhost:5173/", session="my-test", group_title="页面测试")
    text = evaluate("document.body.innerText.slice(0, 500)", session="my-test")
"""

import json
import os
import subprocess
import tempfile
from typing import Any, Dict, Optional

BASE_URL = "http://127.0.0.1:10086/command"


def call(action: str, args: Optional[Dict[str, Any]] = None, session: str = "default", timeout: int = 60) -> Any:
    """发送一个 WebBridge 命令，返回 data 字段；失败抛 RuntimeError。"""
    body = {"action": action, "args": args or {}, "session": session}
    fd, path = tempfile.mkstemp(suffix=".json", prefix="wb-req-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False)
        out = subprocess.run(
            [
                "curl.exe", "-s", "-X", "POST", BASE_URL,
                "-H", "Content-Type: application/json",
                "--data-binary", f"@{path}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    finally:
        os.unlink(path)

    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"webbridge {action}: 无法解析响应（daemon 未运行？）: {out.stdout[:200]}") from e

    if not data.get("ok"):
        raise RuntimeError(f"webbridge {action} failed: {data.get('error') or data}")
    return data["data"]


def navigate(url: str, session: str, new_tab: bool = False, group_title: Optional[str] = None) -> Dict[str, Any]:
    """打开 URL（可选新标签 + 标签组标题）。"""
    args: Dict[str, Any] = {"url": url, "newTab": new_tab}
    if group_title:
        args["group_title"] = group_title
    return call("navigate", args, session)


def evaluate(code: str, session: str, timeout: int = 60) -> Any:
    """在当前标签页执行 JS（支持 async/await），返回 JSON 化的结果。"""
    return call("evaluate", {"code": code}, session, timeout).get("value")


def snapshot(session: str) -> Dict[str, Any]:
    """可访问性树快照（文本结构）。"""
    return call("snapshot", {}, session)


def click(selector: str, session: str) -> Dict[str, Any]:
    """点击元素（@e ref 或 CSS 选择器）。"""
    return call("click", {"selector": selector}, session)


def close_session(session: str) -> int:
    """关闭该 session 的所有标签页（测试收尾用，需用户明确允许）。"""
    return call("close_session", {}, session).get("closed", 0)
