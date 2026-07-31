"""
LLM JSON Utils 单元测试 — 共享 JSON 修复与容错解析工具。

覆盖：
- repair_json: markdown 包裹、尾逗号、单引号、控制字符
- extract_json_object: 平衡括号提取、字符串内括号
- parse_json_tolerant: 文本中嵌入 JSON 的提取
- parse_structured_output: 全流程容错（最强修复）
- 边界场景：空输入、非字符串、无 JSON、不平衡括号
"""

import pytest

from app.services.llm_json_utils import (
    apply_json_repairs,
    extract_first_json_object,
    extract_json_object,
    parse_json_tolerant,
    parse_structured_output,
    repair_json,
)


# ── repair_json ──────────────────────────────────────────

class TestRepairJson:
    """修复常见 LLM JSON 输出问题。"""

    def test_valid_json_passthrough(self):
        """合法 JSON 应直接解析成功。"""
        assert repair_json('{"city": "重庆", "days": 3}') == {"city": "重庆", "days": 3}

    def test_markdown_code_block(self):
        """markdown ```json 包裹应被剥离。"""
        raw = '```json\n{"city": "成都"}\n```'
        assert repair_json(raw) == {"city": "成都"}

    def test_markdown_code_block_uppercase(self):
        """大写 JSON 标识也应被识别。"""
        raw = '```JSON\n{"x": 1}\n```'
        assert repair_json(raw) == {"x": 1}

    def test_markdown_without_language(self):
        """无语言标识的代码块也应被剥离。"""
        raw = '```\n{"y": 2}\n```'
        assert repair_json(raw) == {"y": 2}

    def test_trailing_comma_object(self):
        """对象尾逗号应被修复。"""
        raw = '{"a": 1, "b": 2,}'
        assert repair_json(raw) == {"a": 1, "b": 2}

    def test_trailing_comma_array(self):
        """数组尾逗号应被修复。"""
        raw = '[1, 2, 3,]'
        assert repair_json(raw) == [1, 2, 3]

    def test_single_quote_keys(self):
        """单引号键应转为双引号。"""
        raw = "{'city': '重庆'}"
        assert repair_json(raw) == {"city": "重庆"}

    def test_single_quote_values(self):
        """单引号值应转为双引号。"""
        raw = '{"city": \'成都\'}'
        assert repair_json(raw) == {"city": "成都"}

    def test_text_with_explanation(self):
        """JSON 前后有解释文本时应提取主对象。"""
        raw = '这是您的行程：\n{"trip": {"city": "三亚"}}\n希望您喜欢！'
        assert repair_json(raw) == {"trip": {"city": "三亚"}}

    def test_empty_string(self):
        assert repair_json("") is None

    def test_none_input(self):
        assert repair_json(None) is None  # type: ignore

    def test_non_string_input(self):
        assert repair_json(123) is None  # type: ignore

    def test_no_json_at_all(self):
        """纯文本无 JSON 应返回 None。"""
        assert repair_json("这不是 JSON，没有任何花括号") is None

    def test_nested_structure(self):
        """嵌套结构应正确解析。"""
        raw = '{"trip": {"city": "重庆", "days": [{"day": 1, "items": []}]}}'
        result = repair_json(raw)
        assert result["trip"]["city"] == "重庆"
        assert len(result["trip"]["days"]) == 1

    def test_chinese_content(self):
        """中文内容应正确处理。"""
        raw = '{"城市": "重庆", "景点": ["洪崖洞", "解放碑"]}'
        result = repair_json(raw)
        assert result["城市"] == "重庆"
        assert "洪崖洞" in result["景点"]


# ── extract_json_object ──────────────────────────────────

class TestExtractJsonObject:
    """从文本中提取平衡的 JSON 对象/数组。"""

    def test_simple_object(self):
        assert extract_json_object('{"a": 1}') == '{"a": 1}'

    def test_object_with_prefix(self):
        assert extract_json_object('result: {"a": 1}') == '{"a": 1}'

    def test_simple_array(self):
        assert extract_json_object('[1, 2, 3]') == '[1, 2, 3]'

    def test_nested_braces(self):
        text = '{"outer": {"inner": "value"}}'
        assert extract_json_object(text) == text

    def test_braces_in_string(self):
        """字符串内的括号不应影响平衡计算。"""
        text = '{"desc": "this has {braces} inside"}'
        assert extract_json_object(text) == text

    def test_no_braces(self):
        assert extract_json_object("no braces here") is None

    def test_unbalanced(self):
        """不平衡的括号应返回 None（找不到匹配的闭合）。"""
        assert extract_json_object('{"a": 1') is None


# ── extract_first_json_object ────────────────────────────

class TestExtractFirstJsonObject:
    """提取第一个平衡的 {...} 块（仅对象）。"""

    def test_simple(self):
        assert extract_first_json_object('{"a": 1}') == '{"a": 1}'

    def test_with_prefix_text(self):
        text = '这是结果：{"trip": {"city": "重庆"}} 完成'
        assert extract_first_json_object(text) == '{"trip": {"city": "重庆"}}'

    def test_nested(self):
        text = '{"a": {"b": {"c": 1}}}'
        assert extract_first_json_object(text) == text

    def test_string_with_braces(self):
        """字符串内的花括号不应影响深度计算。"""
        text = '{"desc": "value with } inside"}'
        assert extract_first_json_object(text) == text

    def test_no_braces(self):
        assert extract_first_json_object("no braces") is None

    def test_empty_string(self):
        assert extract_first_json_object("") is None

    def test_unbalanced(self):
        """不平衡的花括号应返回 None。"""
        assert extract_first_json_object('{"a": 1') is None

    def test_escaped_quote_in_string(self):
        """转义引号不应终止字符串。"""
        text = '{"msg": "say \\"hi\\""}'
        assert extract_first_json_object(text) == text


# ── parse_json_tolerant ──────────────────────────────────

class TestParseJsonTolerant:
    """容错解析：先直接解析，失败则提取主对象重试。"""

    def test_valid_json(self):
        result = parse_json_tolerant('{"a": 1, "b": [2, 3]}')
        assert result == {"a": 1, "b": [2, 3]}

    def test_embedded_in_text(self):
        """JSON 嵌入在文本中时应被提取。"""
        text = 'Here is your itinerary: {"trip": {"city": "重庆"}}'
        result = parse_json_tolerant(text)
        assert result == {"trip": {"city": "重庆"}}

    def test_json_with_trailing_text(self):
        text = '{"name": "test"} Hope this helps!'
        result = parse_json_tolerant(text)
        assert result == {"name": "test"}

    def test_not_json(self):
        assert parse_json_tolerant("not json at all") is None

    def test_empty(self):
        assert parse_json_tolerant("") is None

    def test_none(self):
        assert parse_json_tolerant(None) is None  # type: ignore

    def test_chinese_keys(self):
        result = parse_json_tolerant('{"城市": "重庆", "景点": ["洪崖洞"]}')
        assert result == {"城市": "重庆", "景点": ["洪崖洞"]}


# ── parse_structured_output ──────────────────────────────

class TestParseStructuredOutput:
    """结构化输出全流程容错（最强修复）。"""

    def test_valid_json(self):
        result = parse_structured_output('{"city": "重庆"}')
        assert result == {"city": "重庆"}

    def test_markdown_wrapped(self):
        """markdown 包裹应被修复。"""
        result = parse_structured_output('```json\n{"city": "成都"}\n```')
        assert result == {"city": "成都"}

    def test_trailing_comma(self):
        """尾逗号应被修复。"""
        result = parse_structured_output('{"a": 1, "b": 2,}')
        assert result == {"a": 1, "b": 2}

    def test_single_quotes(self):
        """单引号应被修复。"""
        result = parse_structured_output("{'city': '重庆'}")
        assert result == {"city": "重庆"}

    def test_embedded_with_markdown(self):
        """文本+markdown+尾逗号混合场景。"""
        raw = '结果如下：\n```json\n{"trip": {"city": "三亚",},}\n```\n请查收'
        result = parse_structured_output(raw)
        assert result == {"trip": {"city": "三亚"}}

    def test_no_json(self):
        assert parse_structured_output("没有任何 JSON") is None

    def test_empty(self):
        assert parse_structured_output("") is None

    def test_none(self):
        assert parse_structured_output(None) is None  # type: ignore


# ── apply_json_repairs ───────────────────────────────────

class TestApplyJsonRepairs:
    """字符级 JSON 修复（直接操作字符串）。"""

    def test_trailing_comma_object(self):
        assert apply_json_repairs('{"a": 1,}') == '{"a": 1}'

    def test_trailing_comma_array(self):
        assert apply_json_repairs('[1, 2,]') == '[1, 2]'

    def test_single_quote_keys(self):
        result = apply_json_repairs("{'key': 'value'}")
        assert '"key"' in result

    def test_single_quote_values(self):
        result = apply_json_repairs('{"key": \'value\'}')
        assert '"value"' in result
