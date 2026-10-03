#!/usr/bin/env python3
"""env 配置一致性检查 — 合并前跑一次, 避免"改了没生效"

## 为什么需要

`backend/app/core/config.py` 的 `_load_env_files()` 是这样加载的:

```python
for fp in [project_root / ".env", base / ".env"]:   # 先根目录, 再 backend/
    if fp.exists():
        load_dotenv(fp, override=True, encoding="utf-8")   # override=True
```

两个后果:

1. **`backend/.env` 永远覆盖根目录 `.env`** —— 同名变量根目录那份是死的
2. 历史上两份模板的默认值长期不一致(根目录写 `qwen-2.5-7b` / `claude-3.5-sonnet`,
   backend 写 `minimax-m3` / `claude-sonnet-4.6` / `claude-opus-5`),
   而 `backend/.env.example` 配的模型**一个都不在严格白名单里**。

这个脚本不修改任何文件,只报告:

- 实际加载了哪些文件、生效的是哪一份
- 两份模板里同名但取值不同的变量
- 白名单与模板默认值的冲突
- 已废弃但仍出现的变量

## 用法

    python3 scripts/check_env.py            # 检查
    python3 scripts/check_env.py --verbose  # 附带列出全部变量
"""
import argparse
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT_ENV_EXAMPLE = REPO / ".env.example"
BACKEND_ENV_EXAMPLE = REPO / "backend" / ".env.example"
CONFIG_PY = REPO / "backend" / "app" / "core" / "config.py"
WHITELIST_PY = REPO / "backend" / "app" / "agent" / "routing" / "model_whitelist.py"

# v0.9.3 起无人读取, 改它们没有任何效果
DEPRECATED = {
    "TIER_MODEL_LOW", "TIER_FALLBACK_LOW",
    "TIER_MODEL_MEDIUM", "TIER_FALLBACK_MEDIUM",
    "TIER_MODEL_HIGH", "TIER_FALLBACK_HIGH",
}
# 仍在使用, 别跟着 DEPRECATED 一起清掉
STILL_ACTIVE = {"TIER_CLASSIFY_MODEL"}


def parse_env_example(path):
    """解析 .env.example → {KEY: value}, 跳过注释与空行"""
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if re.fullmatch(r"[A-Z_][A-Z0-9_]*", k):
            out[k] = v.strip()
    return out


def parse_whitelist():
    """从 model_whitelist.py 抽出白名单里的模型 id"""
    if not WHITELIST_PY.exists():
        return set()
    src = WHITELIST_PY.read_text(encoding="utf-8")
    body = src.split("MODEL_WHITELIST", 1)[-1].split("DEFAULT_TIER_MODELS", 1)[0]
    return set(re.findall(r'["\']([\w.\-]+/[\w.\-]+)["\']', body))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    print("=" * 70)
    print("env 配置一致性检查")
    print("=" * 70)

    problems = []

    # ---- 1. 加载顺序 ----
    print("\n[1] 实际加载顺序 (来自 config.py)")
    if CONFIG_PY.exists():
        src = CONFIG_PY.read_text(encoding="utf-8")
        if "override=True" in src:
            print("  ✓ 检测到 override=True")
            print("  → 加载顺序: 根 .env  →  backend/.env (后者覆盖前者)")
            print("  → **backend/.env.example 才是权威模板**")
        else:
            print("  ⚠️ config.py 里没找到 override=True, 加载语义可能已变")
            problems.append("config.py 的 _load_env_files() 可能已变, 请复核本脚本")

    # ---- 2. 两份模板的冲突 ----
    print("\n[2] 两份 .env.example 的同名变量冲突")
    root = parse_env_example(ROOT_ENV_EXAMPLE)
    back = parse_env_example(BACKEND_ENV_EXAMPLE)
    conflicts = []
    for k in sorted(set(root) & set(back)):
        if root[k] != back[k]:
            conflicts.append((k, root[k], back[k]))
    if conflicts:
        print(f"  ⚠️ {len(conflicts)} 个变量取值不同 (以 backend/ 为准):")
        for k, rv, bv in conflicts:
            print(f"    {k}")
            print(f"      根目录: {rv or '(空)'}")
            print(f"      backend: {bv or '(空)'}")
        problems.append(f"{len(conflicts)} 个变量在两份模板里冲突")
    else:
        print("  ✓ 无冲突")

    # ---- 3. 白名单冲突 ----
    print("\n[3] backend/.env.example 档位模型 vs 严格白名单")
    wl = parse_whitelist()
    tier_keys = ("TIER_MODEL_LOW", "TIER_MODEL_MEDIUM", "TIER_MODEL_HIGH")
    present = [(k, back[k]) for k in tier_keys if back.get(k)]
    if not wl:
        print("  (未找到白名单定义, 跳过)")
    elif not present:
        # 模板里已无 TIER_MODEL_*, 说明走的是"档位模型只从 user_preferences 表读"的正确形态。
        # 这里要说清楚, 不能打印成"全部在白名单内"—— 那是空真, 会给人虚假安全感。
        print("  ℹ️ 模板未配置 TIER_MODEL_* (v0.10.0 起已移除)")
        print("  → 档位模型实际来源: user_preferences 表 → model_whitelist.DEFAULT_TIER_MODELS 兜底")
        print(f"  → 兜底默认值: {', '.join(sorted(wl & set(['minimax/minimax-m2.7', 'minimax/minimax-m3'])))}")
    else:
        viol = [(k, v) for k, v in present if v not in wl]
        if viol:
            print(f"  ⚠️ {len(viol)} 个档位模型不在 model_whitelist.py 白名单内:")
            for k, v in viol:
                print(f"    {k}={v}")
            print("  → 这些值本身也不生效(档位模型只从 user_preferences 表读),")
            print("    但会让排查的人误以为白名单没起作用")
            problems.append(f"{len(viol)} 个 TIER_MODEL_* 默认值不在白名单内")
        else:
            print(f"  ✓ {len(present)} 个已配置档位模型全部在白名单内")

    # ---- 4. 废弃变量 ----
    print("\n[4] 废弃变量检查")
    found_dep = sorted((set(root) | set(back)) & DEPRECATED)
    if found_dep:
        print(f"  ⚠️ 仍出现: {', '.join(found_dep)}")
        print("  → 已在模板中标注废弃(改这些没有效果), 确认你知道这点")
        problems.append(f"{len(found_dep)} 个已废弃变量仍出现在模板里")
    else:
        print("  ✓ 无废弃变量残留")

    active = sorted((set(root) | set(back)) & STILL_ACTIVE)
    if active:
        print(f"  ✓ 仍在使用: {', '.join(active)} (请勿误删)")

    # ---- 5. 真实 .env 文件 ----
    print("\n[5] 本地 .env 文件")
    for p in (REPO / ".env", REPO / "backend" / ".env"):
        if p.exists():
            print(f"  ✓ 存在: {p.relative_to(REPO)}")
        else:
            print(f"  - 不存在: {p.relative_to(REPO)}")
    print("  → 两者同时存在时 backend/.env 胜出; 只存在根 .env 时它生效")

    if args.verbose:
        print("\n[附] backend/.env.example 全部变量")
        for k in sorted(back):
            print(f"    {k}={back[k]}")
        print(f"\n[附] 白名单模型 ({len(wl)} 个)")
        for m in sorted(wl):
            print(f"    {m}")

    print("\n" + "=" * 70)
    if problems:
        print(f"发现 {len(problems)} 个问题:")
        for p in problems:
            print(f"  - {p}")
        print("=" * 70)
        return 1
    print("✓ 未发现问题")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
