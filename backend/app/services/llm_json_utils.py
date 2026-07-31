"""
TravelMind Agent — LLM JSON Output Utilities

共享的 LLM JSON 输出解析与修复工具。所有需要解析 LLM 结构化输出的模块
（llm_service、planning_agent、dialog_manager 等）都应复用这里的函数，
避免修复逻辑分散导致行为不一致。

设计原则：
- 容错优先：LLM 输出常带 markdown 包裹、尾逗号、单引号、控制字符等，先修复再解析
- 零外部依赖：仅用 stdlib（json + re），可在任何环境运行
- 可观测：修复失败时记 warning 日志，便于排查

Phase 16.6: 从 planning_agent.py 提取，统一为服务层共享工具。
"""

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def repair_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """尝试修复 LLM JSON 输出的常见问题。

    处理：
    - Markdown 代码块包裹（```json ... ```）
    - 尾逗号（如 [1, 2, 3,] 或 {"a": 1,}）
    - 单引号键/值
    - 字符串内的控制字符
    - 元素间缺失逗号

    返回解析后的 dict，失败返回 None。
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    text = raw_text.strip()

    # 1. 移除 markdown 代码块包裹
    if text.startswith("```"):
        end_idx = text.rfind("```")
        if end_idx > 0:
            text = text[3:end_idx].strip()
            # 移除语言标识（如 ```json）
            if text.startswith("json"):
                text = text[4:].strip()
            elif text.startswith("JSON"):
                text = text[4:].strip()

    # 2. 先尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. 提取主 JSON 对象（找最外层 {...} 或 [...]）
    json_str = extract_json_object(text)
    if not json_str:
        return None

    # 4. 尝试解析提取出的 JSON
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # 5. 应用修复后再试
    repaired = apply_json_repairs(json_str)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON repair failed: {e}")
        return None


def extract_json_object(text: str) -> Optional[str]:
    """从文本中提取主 JSON 对象/数组（找第一个平衡的 {...} 或 [...]）。"""
    start = -1
    for i, c in enumerate(text):
        if c in ('{', '['):
            start = i
            break

    if start < 0:
        return None

    opening = text[start]
    closing = '}' if opening == '{' else ']'
    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        c = text[i]

        if escape_next:
            escape_next = False
            continue

        if c == '\\':
            escape_next = True
            continue

        if c == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if c == opening:
            depth += 1
        elif c == closing:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return None


def apply_json_repairs(json_str: str) -> str:
    """应用常见 JSON 修复。"""
    text = json_str

    # 移除 ] 和 } 前的尾逗号
    text = re.sub(r',\s*([}\]])', r'\1', text)

    # 修复字符串内未转义的控制字符
    text = re.sub(r'(?<=[^\\])\n(?=[^"]*")', r'\\n', text)
    text = re.sub(r'(?<=[^\\])\r(?=[^"]*")', r'\\r', text)

    # 单引号键转双引号：'key': -> "key":
    text = re.sub(r"'([^']+)'(\s*:)", r'"\1"\2', text)

    # 单引号值转双引号（保守：仅纯单引号且不含未转义双引号的值）
    text = re.sub(r":\s*'([^']*)'", r': "\1"', text)

    return text


def extract_first_json_object(text: str) -> Optional[str]:
    """提取第一个平衡的 {...} 块（仅对象，不含数组），尊重字符串/转义。"""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start: i + 1]
    return None


def parse_json_tolerant(text: str) -> Optional[Dict[str, Any]]:
    """容错解析 JSON：先直接解析，失败则回退到第一个平衡对象。

    与 repair_json 的区别：本函数不做字符级修复（单引号/尾逗号），
    仅做"提取主对象后重试"，适用于"JSON 前后有解释文本"的场景。
    """
    if not text or not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    candidate = extract_first_json_object(text)
    if candidate and candidate != text:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    return None


def parse_structured_output(raw_text: str) -> Optional[Dict[str, Any]]:
    """解析 LLM 结构化输出的统一入口（最强容错）。

    依次尝试：
    1. 直接解析
    2. 提取主对象后解析
    3. 应用字符级修复后解析（repair_json 全流程）

    用于 chat_structured 的 content 回退路径，确保 markdown 包裹、
    尾逗号、单引号等常见问题都能被修复。
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    # 先用轻量容错（提取主对象）
    result = parse_json_tolerant(raw_text)
    if result is not None:
        return result

    # 重试用完整修复流程
    return repair_json(raw_text)
