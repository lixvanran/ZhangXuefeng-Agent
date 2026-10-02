"""知识库注册表测试 — 纯标准库, 不需要 pydantic/httpx 等三方依赖。

跑法 (在项目根目录):
    python3 tests/test_kb_registry.py
"""
import json
import os
import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")


def _load_by_path(name, relpath):
    """按文件路径加载模块 — 绕开 app.* 包 __init__ (它会 import engine -> dotenv)"""
    path = os.path.join(BACKEND, relpath)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


kbr = _load_by_path("_kb_registry", "app/agent/rag/kb_registry.py")
boost_mod = _load_by_path("_boost", "app/agent/rag/boost.py")

KBRegistry = kbr.KBRegistry
generic_index_text = kbr.generic_index_text
generic_display_text = kbr.generic_display_text
_as_text = kbr._as_text


class TestGenericFallbacks(unittest.TestCase):
    """没声明 schema 的库, 靠通用兜底也能抽索引/展示文本"""

    def test_index_text_from_common_fields(self):
        item = {"name": "计算机科学", "tags": ["热门", "高薪"], "employment_rate": 0.92}
        text = generic_index_text(item)
        self.assertIn("计算机科学", text)
        self.assertIn("热门", text)

    def test_display_text_has_title_and_license(self):
        item = {"name": "某政策", "summary": "要点", "source": "repo-x", "license": "MIT"}
        out = generic_display_text(item)
        self.assertIn("某政策", out)
        self.assertIn("要点", out)
        self.assertIn("MIT", out, "license 必须出现在展示层(开源内容署名要求)")
        self.assertIn("repo-x", out)

    def test_as_text_handles_nested(self):
        self.assertIn("a", _as_text(["a", "b"]))
        self.assertEqual(_as_text(None), "")
        self.assertEqual(_as_text(42), "42")


class TestAutoDiscovery(unittest.TestCase):
    """v0.10.0 的核心承诺: 丢个 json 进目录就能被检索, 不用改任何代码"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = Path(self.tmp)
        self.reg = KBRegistry()

    def _write(self, name, obj):
        (self.dir / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def test_new_kb_file_auto_registers_and_is_searchable(self):
        # 完全未知的库名 —— 旧实现会在 search_knowledge_base 里被 continue 跳过
        self._write("11_brand_new.json", [
            {"name": "新选科政策解读", "text": "物理组选择建议", "tags": ["选科"]},
        ])
        reg = self.reg.load_directory(self.dir)
        self.assertIn("11_brand_new", reg, "新库没有被自动发现")
        kbs = reg["11_brand_new"]
        self.assertEqual(len(kbs.items), 1)
        self.assertIn("新选科政策解读", kbs.index_of(kbs.items[0]),
                      "新库无法抽出索引文本(旧实现就是这个 continue 掉)")

    def test_manifest_overrides_schema(self):
        self._write("12_with_manifest.json", [
            {"alpha": "关键词甲", "beta": "忽略我", "name": "标题"},
        ])
        self._write("12_with_manifest.manifest.json", {
            "index_fields": ["alpha"],
            "display_fields": ["alpha", "beta"],
            "source": "my-repo",
            "license": "Apache-2.0",
        })
        reg = self.reg.load_directory(self.dir)
        kbs = reg["12_with_manifest"]
        self.assertTrue(kbs.custom_schema if hasattr(kbs, "custom_schema") else (kbs.index_fn and kbs.display_fn))
        self.assertIn("关键词甲", kbs.index_of(kbs.items[0]))
        self.assertNotIn("忽略我", kbs.index_of(kbs.items[0]),
                         "manifest 指定的 index_fields 应被严格遵守")
        self.assertEqual(kbs.source, "my-repo")
        self.assertEqual(kbs.license, "Apache-2.0")

    def test_manifest_not_treated_as_kb(self):
        self._write("13_x.json", [{"a": 1}])
        self._write("13_x.manifest.json", {"index_fields": ["a"]})
        reg = self.reg.load_directory(self.dir)
        self.assertIn("13_x", reg)
        self.assertNotIn("13_x.manifest", reg.names, "manifest 文件本身不该被当成知识库")

    def test_license_inferred_from_entries(self):
        self._write("14_lic.json", [
            {"text": "内容1", "source": "Eric-Yibo-Shen/zhangxuefeng-skillset", "license": "CC BY 4.0"},
            {"text": "内容2"},
        ])
        reg = self.reg.load_directory(self.dir)
        kbs = reg["14_lic"]
        self.assertEqual(kbs.license, "CC BY 4.0", "应从条目里自动推断 license")
        self.assertIn("zhangxuefeng-skillset", kbs.source)

    def test_broken_file_is_reported_not_silently_skipped(self):
        (self.dir / "15_broken.json").write_text("{ this is not json", encoding="utf-8")
        self._write("16_good.json", [{"a": "b"}])
        reg = self.reg.load_directory(self.dir)
        self.assertNotIn("15_broken", reg)
        self.assertIn("16_good", reg, "一个坏文件不该拖垮整目录加载")

    def test_non_dict_entries_dropped_with_count(self):
        self._write("17_mixed.json", [{"a": 1}, "not a dict", 42])
        reg = self.reg.load_directory(self.dir)
        self.assertEqual(len(reg["17_mixed"].items), 1, "非 dict 记录应被丢弃而不是让检索崩溃")


class TestRuntimeRegistration(unittest.TestCase):
    """运行时注册 — 热加载/测试用, 不需要重启进程"""

    def test_register_and_search(self):
        reg = KBRegistry()
        reg.register("runtime_kb", [{"name": "运行时条目", "text": "计算机 就业"}],
                     source="hot-load", license="MIT")
        self.assertIn("runtime_kb", reg)
        kbs = reg["runtime_kb"]
        self.assertIn("计算机 就业", kbs.index_of(kbs.items[0]))

    def test_unregister(self):
        reg = KBRegistry()
        reg.register("tmp", [{"a": 1}])
        self.assertTrue(reg.unregister("tmp"))
        self.assertFalse(reg.unregister("tmp"))
        self.assertNotIn("tmp", reg)

    def test_register_rejects_non_list(self):
        reg = KBRegistry()
        with self.assertRaises(TypeError):
            reg.register("bad", {"not": "a list"})

    def test_overwrite_is_logged_not_crashed(self):
        reg = KBRegistry()
        reg.register("dup", [{"a": 1}])
        reg.register("dup", [{"a": 1}, {"a": 2}])   # 重复注册应覆盖而非报错
        self.assertEqual(len(reg["dup"].items), 2)


class TestDescribe(unittest.TestCase):
    """可观测性 — 排查"为什么搜不到"不用翻代码"""

    def test_describe_reports_all_libraries(self):
        reg = KBRegistry()
        reg.register("a", [{"x": 1}], source="s1", license="MIT")
        reg.register("b", [{"x": 1}])
        info = reg.describe()
        self.assertEqual(info["total_libraries"], 2)
        self.assertEqual(info["total_items"], 2)
        names = {lib["name"] for lib in info["libraries"]}
        self.assertEqual(names, {"a", "b"})
        a_meta = next(l for l in info["libraries"] if l["name"] == "a")
        self.assertEqual(a_meta["license"], "MIT")


class TestEntityBoostRevived(unittest.TestCase):
    """v0.10.0 修: boost.py 曾硬编码找不存在的 'gaokao_2026', 永远返回 []"""

    def setUp(self):
        self.boost = boost_mod

    def test_boost_works_with_registry(self):
        reg = KBRegistry()
        reg.register("08_admission_scores", [
            {"province": "湖北", "year": 2025, "min_score": 520, "min_rank": 20000, "school_name": "某大学"},
        ])
        out = self.boost.maybe_apply_boost("湖北 2026 高考分数线", reg)
        self.assertTrue(out, "实体 boost 仍然返回空(死代码没修好)")
        self.assertEqual(out[0].get("province"), "湖北")

    def test_boost_works_with_legacy_dict(self):
        kb = {"08_admission_scores": [
            {"province": "广东", "year": 2025, "min_score": 600, "min_rank": 5000},
        ]}
        out = self.boost.maybe_apply_boost("广东 2026 一本线", kb)
        self.assertTrue(out, "旧 dict 形态也要兼容")

    def test_boost_no_signal_returns_empty(self):
        reg = KBRegistry()
        reg.register("08_admission_scores", [{"province": "湖北"}])
        self.assertEqual(self.boost.maybe_apply_boost("计算机专业怎么样", reg), [])


class TestRealKnowledgeBaseShape(unittest.TestCase):
    """用仓库里真实的 knowledge_base/ 跑一遍, 确认 10 个老库行为不回归"""

    @classmethod
    def setUpClass(cls):
        cls.kb_dir = Path(BACKEND) / "knowledge_base"
        if not cls.kb_dir.exists():
            raise unittest.SkipTest("knowledge_base/ not found")

    def test_all_ten_legacy_libs_load_and_are_searchable(self):
        reg = KBRegistry().load_directory(self.kb_dir)
        info = reg.describe()
        for expected in ("01_persona", "02_quotes", "03_majors", "04_universities",
                         "05_volunteer_strategy", "06_career_employment", "07_life_study",
                         "08_admission_scores", "09_policies", "10_external_kb"):
            self.assertIn(expected, reg, f"老库 {expected} 加载失败")
        self.assertGreaterEqual(info["total_libraries"], 10)
        self.assertGreater(info["total_items"], 500)

    def test_every_entry_produces_nonempty_index_text(self):
        """索引文本抽不出来的条目 = 永远搜不到, 必须能被发现"""
        reg = KBRegistry().load_directory(self.kb_dir)
        empty = []
        for name, kbs in reg.items():
            for it in kbs.items:
                if not kbs.index_of(it).strip():
                    empty.append(name)
                    break
        self.assertEqual(empty, [], f"这些库有条目抽不出索引文本: {empty}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
