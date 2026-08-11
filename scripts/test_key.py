#!/usr/bin/env python3
"""OpenRouter Key 验证脚本 - 不依赖项目代码, 独立可跑

用法:
    python scripts/test_key.py
    python scripts/test_key.py sk-or-v1-your-key-here

会调 OpenRouter 的 /api/v1/auth/key 端点验证 key 是否有效
- 200 → key 有效, 显示关联的账号信息
- 401 → key 无效, 显示具体原因
- 其他 → 网络/服务端问题
"""
import sys
import os
import json
from pathlib import Path

# 加 backend 到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def test_key(key: str) -> int:
    """返回 0 = 通过, 1 = 失败"""
    import httpx

    key = key.strip()
    print(f"\n{'='*60}")
    print(f"  OpenRouter Key 验证")
    print(f"{'='*60}")
    print(f"  Key 前 8 位: {key[:12]}...")
    print(f"  Key 长度: {len(key)}")
    print(f"  Key 字符: {'all ASCII' if all(ord(c) < 128 for c in key) else '含非 ASCII 字符!'}")
    print(f"{'='*60}\n")

    # 调用 OpenRouter 的 /api/v1/auth/key 端点
    print("调用 https://openrouter.ai/api/v1/auth/key ...")
    try:
        r = httpx.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )
    except httpx.ConnectError as e:
        print(f"✗ 网络连接失败: {e}")
        print("  → 可能是网络/防火墙问题, 不是 key 的问题")
        return 1
    except Exception as e:
        print(f"✗ 请求失败: {e}")
        return 1

    print(f"\nHTTP 状态: {r.status_code}")
    try:
        data = r.json()
    except Exception:
        print(f"响应 (非 JSON): {r.text[:500]}")
        return 1

    if r.status_code == 200:
        print("\n✓ Key 有效!\n")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("\n你的 OpenRouter 账号状态正常, key 工作良好。")
        if "data" in data:
            d = data["data"]
            print(f"\n  账号邮箱: {d.get('email', '?')}")
            print(f"  余额: ${d.get('limit_remaining', '?')} (剩余) / ${d.get('limit', '?')} (总额)")
            print(f"  使用: ${d.get('usage', '?')}")
            print(f"  是否免费: {d.get('is_free_tier', '?')}")
        return 0
    elif r.status_code == 401:
        print(f"\n✗ Key 无效! 错误码: 401\n")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("\n可能原因:")
        print("  1. 这个 key 已经被 revoke / 删除")
        print("  2. 这个 key 来自一个已删除的账号")
        print("  3. 你给了 key 但从未在 OpenRouter 后台点过 'Create'")
        print("  4. 账号被风控/暂停 (违规或余额严重不足)")
        print("\n解决步骤:")
        print("  1. 去 https://openrouter.ai/keys 看 key 列表")
        print("  2. 如果列表为空 → 点 'Create Key' 新建一个, 复制完整的 key")
        print("  3. 如果列表有这个 key 但验证失败 → 联系 OpenRouter support")
        print("  4. 把新 key 填到 zhangxuefeng-demo/.env 的 LLM_API_KEY= 后面")
        print("  5. 重启 启动.bat")
        return 1
    else:
        print(f"\n⚠ 异常状态: {r.status_code}\n")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 1


def load_key_from_env() -> str:
    """从项目 .env 读 LLM_API_KEY"""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("LLM_API_KEY=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip()
    return ""


if __name__ == "__main__":
    # 优先级: 命令行参数 > .env
    if len(sys.argv) > 1:
        key = sys.argv[1]
    else:
        key = load_key_from_env()
        if not key:
            print("用法:")
            print("  python scripts/test_key.py              # 用 .env 里的 key")
            print("  python scripts/test_key.py sk-or-v1-... # 用指定的 key")
            print("\n没在 .env 找到 LLM_API_KEY")
            sys.exit(1)
        print(f"(从 .env 读 key)")

    sys.exit(test_key(key))
