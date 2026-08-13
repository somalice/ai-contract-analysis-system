"""
JSON 容错解析工具(Sprint 8.6 - v1.0.0)

职责:
- 从 LLM 输出中提取 JSON 对象(容错)
- 作为 contract_review_agent / generation_agent / bid(json_utils) 的统一规范入口

策略(层层降级):
1. 去除 BOM / 首尾空白
2. 去除 Markdown 代码块包裹(```json ... ``` 或 ``` ... ```)
3. 直接 json.loads
4. 平衡括号匹配提取首个 {...}(跳过字符串内的括号,处理转义)
5. 仍失败 → 返回 None

设计:
- 纯函数,无副作用,不依赖 Flask 上下文
- 行为与原 bid/json_utils.extract_json 完全兼容(向后兼容)
- 额外增强:BOM 去除、首行语言标记去除(```json)
"""
import json
from typing import Optional


def extract_json(text: str) -> Optional[dict]:
    """
    从 LLM 输出中提取 JSON 对象(容错)

    :param text: LLM 输出文本
    :return: dict 或 None(解析失败)
    """
    if not text:
        return None

    # 1. 去除 BOM + 首尾空白
    if text.startswith('\ufeff'):
        text = text.lstrip('\ufeff')
    text = text.strip()

    # 2. 去除 Markdown 代码块包裹(支持 ```json / ``` 等首行语言标记)
    if text.startswith('```'):
        lines = text.split('\n')
        # 去掉首行 ``` 或 ```json
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        # 去掉末行 ```(若存在)
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text = '\n'.join(lines).strip()

    # 3. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 4. 平衡括号匹配提取首个 { ... }
    #    跳过字符串内的括号(处理 \" 转义),避免被 JSON value 中的括号干扰
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None
