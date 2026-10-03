"""搜索相关性门控测试 — 纯标准库 + AST, 不需要依赖

## 为什么需要

2026-10-02 实测发现: HTML 抓取类源会"成功返回但内容与查询无关"。
Bing 对多 term 中文查询退化成只匹配第一个词:

    「强基计划」        → 百科/报考指南/华科招生简章   (词覆盖率 100%)
    「强基计划 报考条件」→ 汉字"强"的字典页面          (词覆盖率   0%)

provider 报 success、条数也正常, **没有任何报错信号**。若直接当证据喂给 LLM,
结果就是"答非所问但附带了看起来很权威的链接" —— 比搜不到更有害。

本测试锁定门控逻辑: 低相关性必须被识别、标记、且明确告知 LLM 不可采信。

跑法 (在项目根目录):
    python3 tests/test_search_relevance.py
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _search_stubs import ws  # noqa: E402  共享桩环境

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO, "backend")


class TestRelevanceScoring(unittest.TestCase):
    """词覆盖率计算"""

    def test_relevant_results_score_high(self):
        results = [
            {"title": "2026年强基计划报考指南", "content": "强基计划报考条件与流程详解"},
            {"title": "强基计划招生简章汇总", "content": "各高校强基计划报名时间"},
        ]
        score = ws._relevance("强基计划 报考条件", results)
        self.assertGreater(score, ws.MIN_SEARCH_RELEVANCE,
                           f"明显相关的结果被误判为低可信: {score:.0%}")

    def test_garbage_results_score_low(self):
        """复现真实故障: 强基计划 报考条件 → 汉字"强"的字典页"""
        results = [
            {"title": "强（汉语汉字）_百度百科", "content": "强，汉语汉字，读音qiáng"},
            {"title": "强的意思,强的解释,强的拼音", "content": "汉语国学字典"},
            {"title": "强怎么读_强的拼音 - 新华字典", "content": "新华字典在线查词"},
        ]
        score = ws._relevance("强基计划 报考条件", results)
        self.assertLess(score, ws.MIN_SEARCH_RELEVANCE,
                        f"答非所问的结果没有被门控拦住: {score:.0%}")

    def test_empty_results_score_zero(self):
        self.assertEqual(ws._relevance("强基计划 报考条件", []), 0.0)

    def test_query_without_terms_is_not_judged(self):
        """拆不出实义词时不该误判"""
        self.assertEqual(ws._relevance("？", [{"title": "x"}]), 1.0)

    def test_threshold_is_sane(self):
        self.assertGreater(ws.MIN_SEARCH_RELEVANCE, 0.0)
        self.assertLess(ws.MIN_SEARCH_RELEVANCE, 1.0)


class TestStopWordsStripped(unittest.TestCase):
    def test_question_words_not_counted(self):
        terms = ws._query_terms("计算机专业 怎么样")
        self.assertIn("计算机专业", terms)
        self.assertNotIn("怎么样", terms, "虚词不该计入分母, 否则永远拉低覆盖率")


class TestGateIsWiredIntoResult(unittest.TestCase):
    """门控必须真的出现在 web_search 的返回体里"""

    def test_success_path_emits_relevance_fields(self):
        src = open(os.path.join(BACKEND, "app/agent/search/web_search.py"), encoding="utf-8").read()
        self.assertIn('"relevance"', src, "成功返回缺少 relevance 字段")
        self.assertIn('"low_relevance"', src, "成功返回缺少 low_relevance 字段")
        self.assertIn("_relevance(query, final)", src,
                      "门控函数没有被真正调用")

    def test_failure_path_marks_low_relevance(self):
        src = open(os.path.join(BACKEND, "app/agent/search/web_search.py"), encoding="utf-8").read()
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "web_search")
        ret = next(n for n in ast.walk(fn) if isinstance(n, ast.Return))
        keys = {k.value for d in ast.walk(ret)
                if isinstance(d, ast.Dict)
                for k in d.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        self.assertIn("low_relevance", keys, "全失败路径也应带 low_relevance=True")


class TestPromptWarnsLLM(unittest.TestCase):
    """最关键的一环: 低相关性必须变成给 LLM 的硬指令, 而不只是日志里一行"""

    def setUp(self):
        with open(os.path.join(BACKEND, "app/agent/tools/web.py"), encoding="utf-8") as f:
            self.src = f.read()

    def test_format_reads_low_relevance(self):
        self.assertIn('result.get("low_relevance"', self.src)

    def test_prompt_tells_llm_not_to_use_results(self):
        self.assertIn("不可作为答案依据", self.src,
                      "低相关性时必须明确禁止 LLM 采信这些结果")
        self.assertIn("不要引用或复述", self.src,
                      "低相关性时必须要求 LLM 不要引用结果")

    def test_prompt_offers_verification_path(self):
        """给用户一条可执行的核实路径, 而不是一句"搜不到"了事"""
        self.assertIn("gaokao.chsi.com.cn", self.src,
                      "低相关性时应引导用户去权威渠道核实")

    def test_relevance_shown_in_overview(self):
        self.assertIn("查询词覆盖率", self.src, "概览里应展示词覆盖率, 便于事后复盘")


if __name__ == "__main__":
    unittest.main(verbosity=2)
