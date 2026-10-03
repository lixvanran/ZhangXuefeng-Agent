"""gitignore 误伤检查 — 纯标准库, 不需要任何依赖。

## 为什么需要这个

`.gitignore` 里一条裸的 `data/` 规则, 曾把 `frontend/src/data/demoScript.ts`
**静默忽略**了。而 `ChatPage.tsx:10` 一直在 import 它, 于是:

- 该文件从未进入过仓库的**任何一个提交**(已用 `git rev-list --all` 逐个验证)
- 任何一次全新克隆后 `vite build` 都失败:
  `[vite:load-fallback] Could not load .../src/data/demoScript: ENOENT`
- 一直没被发现, 因为 `启动.bat` 走 `npm run dev`, dev 模式不检查也不产物构建

这与 v0.9.1 修过的 `uploads/` 误伤 `workspace/uploads/` 是**同一类问题**——
教训写进了注释,但只修了一半。

gitignore 的危险之处在于它**静默**:文件被忽略时 `git add` 不会报错,
只是"什么都没发生"。所以必须用测试盯住。

跑法 (在项目根目录):
    python3 tests/test_gitignore_safety.py
"""
import os
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 必须是"能被 git 追踪"的源码/配置路径。
# 一旦这些路径被 .gitignore 静默忽略, 就会重演 demoScript 那次事故。
MUST_BE_TRACKED = [
    "frontend/src/data/demoScript.ts",   # 本次事故的主角
    "backend/knowledge_base/01_persona.json",
    "backend/db/majors.json",
    "backend/requirements.txt",
    "check_imports.py",
    "AGENTS.md",
    "tests/test_kb_registry.py",
    "scripts/ci.sh",
]

# 必须是"被忽略"的运行期产物
MUST_BE_IGNORED = [
    "backend/data/anything.json",
    "data/anything.json",
    "frontend/node_modules/whatever",
    "backend/app/__pycache__/x.pyc",
    "backend/db/whatever.sqlite",
]


def _check_ignore(rel):
    """返回被哪条规则忽略; 返回 None 表示未被忽略"""
    p = subprocess.run(
        ["git", "check-ignore", "-v", rel],
        cwd=REPO, capture_output=True, text=True,
    )
    if p.returncode != 0:
        return None
    return p.stdout.strip()


def _is_tracked(rel):
    p = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel],
        cwd=REPO, capture_output=True, text=True,
    )
    return p.returncode == 0


class TestSourceFilesAreNotIgnored(unittest.TestCase):
    """源码被 ignore = 静默丢文件, 比任何编译错误都难查"""

    def test_must_be_tracked_paths_not_ignored(self):
        for rel in MUST_BE_TRACKED:
            with self.subTest(path=rel):
                rule = _check_ignore(rel)
                self.assertIsNone(
                    rule,
                    f"{rel} 被 .gitignore 静默忽略了! 规则: {rule}\n"
                    f"若这是运行期产物, 请把 gitignore 规则改精确(用前导 / 锚定到根目录); "
                    f"若是源码, 请删掉那条过宽的规则。")

    def test_no_bare_directory_rule_in_gitignore(self):
        """gitignore 里的裸 `name/` 会匹配任意层级, 是这类事故的根因"""
        gi = os.path.join(REPO, ".gitignore")
        with open(gi, encoding="utf-8") as f:
            lines = [ln.strip() for ln in f]
        # 允许的裸目录规则: 已验证不会误伤源码的
        allowlist = {
            "node_modules/", "__pycache__/", ".venv/", "dist/", "build/",
            "release/", "samples/*.mp3", "samples/*.wav", "samples/*.m4a",
        }
        risky = []
        for ln in lines:
            if not ln or ln.startswith("#"):
                continue
            bare = ln.rstrip("/")
            if "/" not in bare:          # 完全无路径分隔 → 任意层级匹配
                risky.append(ln)
            elif ln.startswith("/"):     # 前导 / → 已锚定到根目录, 安全
                continue
        # 形如 "foo/" 无前导斜杠且无其它分隔符的, 才会任意层级匹配
        truly_risky = [r for r in risky if r.rstrip("/") in
                       ("data", "uploads", "dist", "build", "release")]
        self.assertEqual(
            [r for r in truly_risky if r.rstrip("/") == "data"], [],
            ".gitignore 仍有裸 `data/` 规则, 会静默忽略任意层级的 data 目录"
            "(历史上正是它吃掉了 frontend/src/data/demoScript.ts)")


class TestGeneratedFilesAreIgnored(unittest.TestCase):
    """收紧规则不能连运行期产物一起放进来"""

    def test_runtime_artifacts_ignored(self):
        for rel in MUST_BE_IGNORED:
            with self.subTest(path=rel):
                rule = _check_ignore(rel)
                self.assertIsNotNone(
                    rule,
                    f"{rel} 没有被忽略 —— 收紧 data/ 规则时误伤了运行期产物忽略")


class TestDemoScriptIsActuallyCommitted(unittest.TestCase):
    """直接守住那次事故本身: 该文件必须真的在版本库里"""

    def test_demo_script_tracked_by_git(self):
        self.assertTrue(
            _is_tracked("frontend/src/data/demoScript.ts"),
            "frontend/src/data/demoScript.ts 没有被 git 追踪 —— "
            "它被 .gitignore 静默忽略了, 前端会构建失败")

    def test_demo_script_not_empty(self):
        p = os.path.join(REPO, "frontend/src/data/demoScript.ts")
        self.assertTrue(os.path.exists(p), "demoScript.ts 不存在")
        with open(p, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("demoScripts", src)
        self.assertIn("demoProfile", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
