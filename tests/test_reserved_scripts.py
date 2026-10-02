"""预留脚本状态锁定 — 纯标准库 + AST, 不需要运行时依赖。

背景: scripts/ 下有 4 个与「真实公众人物声音克隆」相关的脚本。
2026-10-02 决策为「保留但标记预留」, 不删除、不开发、不接入运行时。

本测试同时锁定两件事(缺一不可):
  1. 这 4 个文件仍然存在        —— 防止被误删
  2. 它们仍处于休眠状态        —— 防止被悄悄接入主链路

第二点才是重点: 一个"预留"的代码如果哪天被接进了运行时,
合规风险就从"潜在"变成"实际", 必须让 CI 在那一刻报红。

跑法 (在项目根目录):
    python3 tests/test_reserved_scripts.py
"""
import ast
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RESERVED = (
    "scripts/clone_zhang_voice.py",
    "scripts/download_zhang_audio.py",
    "scripts/generate_demo_voice.py",
    "samples/INSTRUCTIONS.md",
)


def _read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


class TestReservedScriptsStillPresent(unittest.TestCase):
    """预留 ≠ 删除。文件必须还在, 否则维护者会忘记这段历史"""

    def test_all_reserved_files_exist(self):
        for rel in RESERVED:
            with self.subTest(path=rel):
                self.assertTrue(
                    os.path.exists(os.path.join(REPO, rel)),
                    f"{rel} 被删除了 —— 预留状态意味着保留, 移除需先走决策(见 scripts/RESERVED.md)")

    def test_reserved_readme_exists(self):
        self.assertTrue(
            os.path.exists(os.path.join(REPO, "scripts/RESERVED.md")),
            "scripts/RESERVED.md 缺失 —— 预留脚本失去状态说明, 后续维护者会误用")

    def test_reserved_readme_covers_every_reserved_file(self):
        doc = _read("scripts/RESERVED.md")
        for rel in RESERVED:
            name = os.path.basename(rel)
            with self.subTest(path=rel):
                self.assertIn(name, doc, f"RESERVED.md 未提及 {name}")


class TestReservedScriptsAreMarked(unittest.TestCase):
    """单独打开任一文件时, 都能看到它是预留状态"""

    def test_every_reserved_file_has_marker(self):
        for rel in RESERVED:
            with self.subTest(path=rel):
                head = _read(rel)[:800]
                self.assertIn(
                    "RESERVED", head,
                    f"{rel} 开头缺少 [预留 / RESERVED] 标记")

    def test_marker_points_to_readme(self):
        for rel in RESERVED:
            with self.subTest(path=rel):
                self.assertIn("RESERVED.md", _read(rel)[:800],
                              f"{rel} 的标记未指向 scripts/RESERVED.md")


class TestVoiceCloningStaysDormant(unittest.TestCase):
    """核心: 预留状态 = 休眠。接入运行时即视为合规风险升级, 必须失败"""

    def test_synthesize_speech_still_returns_none(self):
        src = _read("backend/app/services/tts_service.py")
        tree = ast.parse(src)
        fn = next((n for n in tree.body
                   if isinstance(n, ast.AsyncFunctionDef) and n.name == "synthesize_speech"), None)
        self.assertIsNotNone(fn, "synthesize_speech() 不见了 —— TTS 架构可能已变, 请重新评估本文件")

        returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
        self.assertTrue(returns, "synthesize_speech() 没有 return 语句")
        for r in returns:
            val = r.value
            if val is None:
                continue  # 裸 return
            # 合法形态只有 `return None` / `return None  # 注释`
            is_none_const = isinstance(val, ast.Constant) and val.value is None
            self.assertTrue(
                is_none_const,
                "synthesize_speech() 开始返回非 None —— "
                "后端重新合成音频了。声音克隆链路可能已被激活, "
                "请先走 scripts/RESERVED.md 里的合规决策再改这里")

    def test_voice_id_has_no_reader(self):
        """ZHANG_VOICE_ID 只能被声明, 不能被读取 —— 读取即代表被接入"""
        offenders = []
        for dirpath, dirnames, filenames in os.walk(os.path.join(REPO, "backend", "app")):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fn)
                if path.endswith(os.path.join("core", "config.py")):
                    continue  # 声明处不算
                src = _read(os.path.relpath(path, REPO))
                for pat in (r"\.ZHANG_VOICE_ID\b", r"getattr\([^)]*[\"']ZHANG_VOICE_ID[\"']"):
                    import re
                    if re.search(pat, src):
                        offenders.append(os.path.relpath(path, REPO))
        self.assertEqual(
            offenders, [],
            f"ZHANG_VOICE_ID 被读取了(预留脚本可能已接入主链路): {offenders}")


class TestNoReservedDependencyInRequirements(unittest.TestCase):
    """声音克隆依赖不应随预留状态一起进主依赖链"""

    def test_no_minimax_tts_requirement(self):
        req = _read("backend/requirements.txt")
        for bad in ("minimax", "edge-tts", "elevenlabs", "clone_voice"):
            with self.subTest(pkg=bad):
                line = [ln for ln in req.split("\n")
                        if bad in ln.lower() and not ln.strip().startswith("#")]
                self.assertEqual(line, [],
                                 f"requirements.txt 出现了 {bad} —— "
                                 f"若已接入 TTS, 请先完成 scripts/RESERVED.md 的合规决策")


if __name__ == "__main__":
    unittest.main(verbosity=2)
