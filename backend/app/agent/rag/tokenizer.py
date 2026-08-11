"""中文分词器 - 支持中英文 + bigram
v0.7.9.6 fix: 旧 regex 把'湖北'切成 ['湖','北'], 现在用 `[\u4e00-\u9fff]+` 切连续中文 + 2 字符 bigram
"""
import re
from typing import List


def tokenize(text: str) -> List[str]:
    """分词, 返回小写 token 列表
    - ASCII run (英文/数字): 整体
    - Chinese run (连续中文): 整体 + 所有 2 字符 bigram
    """
    text = (text or "").lower()
    tokens = []
    for tok in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text):
        if re.match(r"[\u4e00-\u9fff]+", tok):
            for i in range(len(tok) - 1):
                tokens.append(tok[i:i + 2])
            tokens.append(tok)
        else:
            tokens.append(tok)
    return tokens
