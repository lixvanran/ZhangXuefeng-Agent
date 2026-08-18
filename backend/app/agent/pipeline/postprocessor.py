"""后处理 - 清理 LLM 输出的 raw tool call / 占位文本
v0.7.5: 防止 LLM 漏出 <invoke>/<tool_call>/<minimax> 等 tag
"""
import re as _re


def sanitize_llm_output(text: str) -> str:
    """Strip accidental tool-call XML / placeholder text that some LLMs
    write into the visible narrative.

    处理:
    - 零宽字符 ( etc)
    - <invoke name="...">...</invoke>
    - <tool_call>...</tool_call>
    - ]<minimax>[<query>...
    - ]<]minimax[>[
    - query_college<arg_key>...</arg_key>... 这种 raw function call
    - 单独 <arg_key>/<arg_value> tags
    - v0.9.8: <invokename="...">Args<parametername="..."><parameter>...</parameter>...
            (Anthropic 风格幻觉 tool_call, 一些 LLM 训练数据里的格式)
    """
    if not text:
        return text
    s = text
    # 零宽字符
    s = s.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    # <invoke name="...">...</invoke>
    s = _re.sub(r'<invoke\b[^>]*>[\s\S]*?</invoke>', '', s)
    # <tool_call>...</tool_call>
    s = _re.sub(r'<\s*/?\s*tool_call\s*>', '', s)
    s = _re.sub(r'<\s*/?\s*invoke\s*>', '', s)
    # v0.9.8: Anthropic 风格幻觉 — <invokename="xxx">Args<parametername="..."><parameter>{...}</parameter>
    # 这种格式 LLM 经常误用, 整段去掉
    s = _re.sub(
        r'<\s*invokename\s*=\s*"[^"]+"\s*>[\s\S]*?(?=\n\n|\Z)',
        '',
        s,
    )
    # 单独的 <parameter>/<parametername>/<parameter_value> 等标签
    s = _re.sub(r'<\s*/?\s*parametername\s*>', '', s)
    s = _re.sub(r'<\s*/?\s*parameter_value\s*>', '', s)
    s = _re.sub(r'<\s*/?\s*parameter\s*>', '', s)
    s = _re.sub(r'>\s*Args\s*<', ' ', s)  # ">Args<" → 空格
    # raw "Args" 单独出现
    s = _re.sub(r'\bArgs\b', '', s)
    # ]<minimax>[<query>...</query>]
    s = _re.sub(r'\]\s*<\s*minimax\s*>\s*\[\s*<query>[\s\S]*?</query>\s*\]', '', s)
    # ]<]minimax[>[
    s = _re.sub(r'\]<\]minimax\[>\[', '', s)
    # ]<minimax[>[ or ]<minimax>[
    s = _re.sub(r'\]<[^\[]*?minimax[^\]]*?>\[', '', s)
    # 单行 ]<...>[ 纯占位
    s = _re.sub(r'^\s*\][^\n]*?>\[\s*$', '', s, flags=_re.MULTILINE)
    # 独立 <minimax> 标签
    s = _re.sub(r'<\s*minimax\s*>', '', s)
    s = _re.sub(r'<\s*/\s*minimax\s*>', '', s)
    # raw function call blocks: query_college<arg_key>...
    s = _re.sub(
        r'\b(?:query_college|query_major|query_admission|search_web|get_weather)\s*<\s*arg_key\b[\s\S]*?(?:</arg_key>|$)',
        '', s
    )
    # orphan <arg_key>/<arg_value> tags
    s = _re.sub(r'<\s*/?\s*arg_(?:key|value)\s*>', '', s)
    # 压缩空白
    s = _re.sub(r'[ \t]+', ' ', s)
    s = _re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()
