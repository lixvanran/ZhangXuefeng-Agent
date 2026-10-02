#!/usr/bin/env bash
# 本地 CI — 复现 .github/workflows/ci.yml 的全部检查
#
# 为什么不直接用 GitHub Actions:
#   .github/workflows/ci.yml 已写好, 但当前 PAT / GitHub App 都缺 `workflows`
#   scope, 推送被 GitHub 拒绝(普通文件能写, workflow 文件被拒)。
#   补齐权限前, 用这个脚本在本地跑同一套检查。
#
# 用法:
#   bash scripts/ci.sh              # 跑全部
#   bash scripts/ci.sh --fast       # 跳过前端(npm ci 较慢)
#
# 退出码: 任一检查失败即非 0

set -uo pipefail
cd "$(dirname "$0")/.."

FAST=0
[ "${1:-}" = "--fast" ] && FAST=1

FAILED=()
PASSED=()

step() {
    local name="$1"; shift
    printf '\n\033[1m── %s\033[0m\n' "$name"
    if "$@"; then
        PASSED+=("$name")
    else
        FAILED+=("$name")
    fi
}

# ===== 后端: 全部只用标准库, 不需要装三方依赖 =====

step "内部 import 解析"        python3 check_imports.py
step "后端全量语法编译"         python3 -m compileall -q backend/app
step "后端脚本语法编译"         python3 -m compileall -q scripts
# 用例数动态取, 避免硬编码后与实际脱节
N_TESTS=$(python3 -m unittest discover -s tests -p "test_*.py" 2>&1 \
          | sed -n 's/^Ran \([0-9]*\) tests\?.*/\1/p' | head -1)
N_TESTS=${N_TESTS:-?}
step "单元测试 (${N_TESTS} 用例)" python3 -m unittest discover -s tests -p "test_*.py" -v
step "env 配置一致性"           python3 scripts/check_env.py
step "搜索基线自检(离线)"       python3 scripts/search_baseline.py --self-test

# ===== 前端 =====

if [ "$FAST" -eq 1 ]; then
    printf '\n\033[1m── 前端检查已跳过 (--fast)\033[0m\n'
else
    if [ ! -d frontend/node_modules ]; then
        printf '\n\033[1m── 安装前端依赖\033[0m\n'
        # --ignore-scripts 是必需的: electron 的 postinstall 要下 ~100MB 二进制,
        # 网络不佳时会失败, 且 npm ci 失败前会先清空 node_modules, 反而更糟。
        # tsc / vite build 都不需要它。启动.bat:110 用的也是这个参数。
        (cd frontend && npm ci --no-audit --no-fund --ignore-scripts) \
            && PASSED+=("npm ci") \
            || FAILED+=("npm ci")
    fi
    step "前端 TypeScript 类型检查" bash -c "cd frontend && npx tsc --noEmit"
    step "前端构建"                 bash -c "cd frontend && npm run build"
fi

# ===== 汇总 =====

printf '\n\033[1m════════════════════════════════════════\033[0m\n'
for p in "${PASSED[@]:-}"; do [ -n "$p" ] && printf '  \033[32m✓\033[0m %s\n' "$p"; done
for f in "${FAILED[@]:-}"; do [ -n "$f" ] && printf '  \033[31m✗\033[0m %s\n' "$f"; done
printf '\033[1m════════════════════════════════════════\033[0m\n'

if [ ${#FAILED[@]} -gt 0 ]; then
    printf '\033[31m%d 项失败\033[0m\n' "${#FAILED[@]}"
    exit 1
fi
printf '\033[32m全部通过 (%d 项)\033[0m\n' "${#PASSED[@]}"
