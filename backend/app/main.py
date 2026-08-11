"""FastAPI main"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.core.config import settings
from app.db.database import init_db
from app.routers import chat, resources, conversations, user, tts
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info("=" * 60)
    init_db()
    logger.info("DB initialized")

    # Log config
    logger.info(f"LLM: {settings.LLM_MODEL} @ {settings.LLM_BASE_URL}")
    if not settings.LLM_API_KEY:
        logger.warning("LLM_API_KEY not set! LLM calls will fail.")

    # Embedding provider
    if settings.embedding_provider == "openai":
        logger.info(f"Embedding: OpenAI ({settings.OPENAI_EMBEDDING_MODEL})")
    else:
        logger.info("Embedding: local TF-IDF (fallback, 零依赖, 语义弱)")

    # Search provider
    logger.info(f"Search: {settings.search_provider}")

    # TTS
    if settings.MINIMAX_API_KEY:
        logger.info(f"TTS: MiniMax ({settings.MINIMAX_TTS_MODEL})")
    else:
        logger.info("TTS: disabled (no MINIMAX_API_KEY)")

    # Routing
    from app.agent.routing import get_tier_router, get_classifier
    router = get_tier_router()
    logger.info(f"Routing: classifier ready, tiers configured")

    # ★ 启动自检: ping 一下 OpenRouter 验证 key 是否有效
    # 不通过也不报错, 只在日志里告警
    await self_check_openrouter()

    # v0.8.0: 启动时检测 high 档的 Claude Opus 5 / Anthropic 系列在你的 key 下是否可用
    # 实测 2026-07-28: 一些 OpenRouter key 被 Anthropic 区域限制, 调 Claude 会 403
    # 不阻断启动, 只在日志里告警
    await self_check_anthropic_access()

    yield
    logger.info("Shutting down...")


async def self_check_openrouter():
    """启动时调 /api/v1/auth/key 验证, 不消耗 token
    - 200 → ✓ key 有效 (会显示余额)
    - 401 → ✗ 立刻告诉用户去哪修
    """
    if not settings.LLM_API_KEY:
        logger.error(
            "✗ LLM_API_KEY 未设置! 任何消息都会报 401. "
            "请编辑 .env 填上 OpenRouter key 再重启。"
        )
        return
    try:
        import httpx
        r = await httpx.AsyncClient().get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            logger.info(
                f"✓ OpenRouter self-check OK "
                f"(账号={data.get('email','?')}, "
                f"余额=${data.get('limit_remaining','?')}/${data.get('limit','?')}, "
                f"免费档={data.get('is_free_tier','?')})"
            )
        elif r.status_code == 401:
            logger.error(
                f"✗ OpenRouter key 无效 (401 User not found)!\n"
                f"  当前 key 前 8 位: {settings.LLM_API_KEY[:12]}...\n"
                f"  你的 .env 里这个 key OpenRouter 不认账\n"
                f"  解决:\n"
                f"    1) 去 https://openrouter.ai/keys 看 key 列表里有没有这个\n"
                f"    2) 没有 → Create 一个新的, 复制完整 key 贴到 .env\n"
                f"    3) 有但失败 → 它已经被 disable, 重新 Create\n"
                f"    4) 都搞不定 → 跑 python scripts/test_key.py 看具体错\n"
                f"  提示: 可在浏览器打开 http://localhost:3000 → 左下'系统诊断'"
            )
        else:
            logger.warning(f"⚠ OpenRouter self-check 异常: HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"⚠ OpenRouter self-check failed: {e}")


async def self_check_anthropic_access():
    """v0.8.0: 启动时检测 high 档 primary 在你的 key 下能不能调
    - 200 → ✓ high 档 primary 可用
    - 403 "not available in your region" → ✗ 你的 key 被地区限制, 会降级
    - 402 → 余额不足
    - 只在 high 档是 anthropic 系列时才测试 Claude, 其他系列 (Llama 4 Maverick, GPT 等) 跳过
    """
    if not settings.LLM_API_KEY:
        return
    primary = (settings.TIER_MODEL_HIGH or "").lower()
    if "anthropic" not in primary:
        # high 档不是 Claude, 不需要这种探测
        # (用户 2026-07-28: high 档换了, 不是 Claude 了)
        if any(k in primary for k in ["openai/", "google/", "gpt", "gemini"]):
            # 探测 GPT/Gemini — 顺便告诉用户
            await _probe_high_tier_access(settings.TIER_MODEL_HIGH, "high 档 (OpenAI/Google)")
        return
    # 以下是 anthropic 的检测逻辑 (保留代码但不当前不执行)
    try:
        import httpx
        # 用 cheapest 的 haiku 测一下, 不浪费 token
        r = await httpx.AsyncClient().post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": settings.OPENROUTER_REFERER,
                "X-Title": settings.OPENROUTER_TITLE,
            },
            json={
                "model": "anthropic/claude-3-haiku-20240307",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            },
            timeout=15,
        )
        if r.status_code == 200:
            logger.info("✓ Anthropic Claude 可用, high 档会优先走 Opus 5")
        elif r.status_code == 403:
            err = r.json().get("error", {}).get("message", "")
            if "region" in err.lower() or "not available" in err.lower():
                logger.warning(
                    f"⚠ Anthropic Claude 在你的 key 下不可用 (403 region 限制)\n"
                    f"  high 档 primary={settings.TIER_MODEL_HIGH} 会调不通, 自动降级到 fallback 链\n"
                    f"  解决选项:\n"
                    f"    1) 换可调 Claude 的 key (绕开地区限制)\n"
                    f"    2) 把 high 档 primary 改成能调的模型 (z-ai/glm-5.2, minimax/minimax-m2.7 等)\n"
                    f"    3) 不改, 让 fallback 顶上去 (当前默认行为, 已配好 z-ai/glm-5.2 在第一顺位)"
                )
            else:
                logger.warning(f"⚠ Anthropic Claude 403: {err[:200]}")
        elif r.status_code == 402:
            logger.warning("⚠ Anthropic Claude 402: 余额不足, high 档会降级")
        else:
            logger.warning(f"⚠ Anthropic Claude 探测异常: HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"⚠ Anthropic Claude 探测失败: {e}")


async def _probe_high_tier_access(model: str, label: str):
    """v0.8.0: 探测 high 档 primary 是否可用
    - 200 → ✓
    - 403 region → ✗ 会降级
    - 402 → 余额不足
    """
    if not settings.LLM_API_KEY:
        return
    try:
        import httpx
        r = await httpx.AsyncClient().post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": settings.OPENROUTER_REFERER,
                "X-Title": settings.OPENROUTER_TITLE,
            },
            json={"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
            timeout=15,
        )
        if r.status_code == 200:
            logger.info(f"✓ {label} ({model}) 可用, high 档会优先走它")
        elif r.status_code == 403 and ("region" in r.text.lower() or "not available" in r.text.lower()):
            logger.warning(
                f"⚠ {label} ({model}) 调不通 (403 region)\n"
                f"  high 档会自动降级到 fallback 链"
            )
        elif r.status_code == 402:
            logger.warning(f"⚠ {label} ({model}) 402 余额不足")
        else:
            logger.warning(f"⚠ {label} ({model}) HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"⚠ {label} ({model}) 探测失败: {e}")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(settings.UPLOAD_DIR)), name="uploads")

app.include_router(chat.router)
app.include_router(resources.router)
app.include_router(conversations.router)
app.include_router(user.router)
app.include_router(tts.router)


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "endpoints": {
            "frontend": "http://localhost:3000",
            "api_docs": "/docs",
        }
    }


@app.get("/api/health")
async def health():
    """基础健康检查 (不调 LLM, 快速)"""
    return {
        "status": "ok",
        "llm_configured": bool(settings.LLM_API_KEY),
        "llm_model": settings.LLM_MODEL,
        "embedding_provider": settings.embedding_provider,
        "search_provider": settings.search_provider,
        "tts_enabled": bool(settings.MINIMAX_API_KEY),
    }


@app.get("/api/diagnose")
async def diagnose():
    """深度诊断 - 调 OpenRouter /api/v1/auth/key 验证 key 有效性
    - 成功 → key 有效, 显示账号 + 余额
    - 401 → key 无效, 给具体原因和解决步骤
    - 其他错误 → 给原始错误信息
    - v0.8.0: 同时检查 Claude 系列可不可用 (high 档可能配的 Anthropic 模型)
    """
    import httpx
    result = {
        "llm_api_key_set": bool(settings.LLM_API_KEY),
        "llm_api_key_prefix": settings.LLM_API_KEY[:12] + "..." if settings.LLM_API_KEY else None,
        "llm_base_url": settings.LLM_BASE_URL,
        "embedding_provider": settings.embedding_provider,
        "search_provider": settings.search_provider,
        "tts_enabled": bool(settings.MINIMAX_API_KEY),
    }
    if not settings.LLM_API_KEY:
        result["llm_test"] = {
            "ok": False,
            "error": "LLM_API_KEY 未设置",
            "actions": ["编辑 .env, 在 LLM_API_KEY= 后面填上你的 OpenRouter key, 重启 启动.bat"],
        }
        return result
    # 用 OpenRouter 自家的 /api/v1/auth/key 端点验证, 不消耗 token
    try:
        r = await httpx.AsyncClient().get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            result["llm_test"] = {
                "ok": True,
                "model": "auth validated",
                "message": "✓ OpenRouter key 有效",
                "account": {
                    "email": data.get("email"),
                    "is_free_tier": data.get("is_free_tier"),
                    "limit": data.get("limit"),
                    "limit_remaining": data.get("limit_remaining"),
                    "usage": data.get("usage"),
                    "rate_limit": data.get("rate_limit"),
                },
            }
        elif r.status_code == 401:
            data = r.json()
            result["llm_test"] = {
                "ok": False,
                "error_code": 401,
                "error": data.get("error", {}).get("message", "Unknown 401"),
                "diagnosis": "key 格式对, 但 OpenRouter 找不到这个 key 对应的账号",
                "actions": [
                    "1. 去 https://openrouter.ai/keys 看这个 key 是否在列表里",
                    "2. 如果不在 → 点 'Create Key' 重新生成一个, 复制完整 key 到 .env",
                    "3. 如果在列表但验证失败 → 这个 key 已经被 disable/revoke 了, 重新 Create",
                    "4. 如果怎么都创不出能用的 key → 联系 OpenRouter support, 可能是账号问题",
                    "5. 验证 key 是否有效: python scripts/test_key.py",
                ],
            }
        elif r.status_code == 429:
            result["llm_test"] = {
                "ok": False,
                "error_code": 429,
                "error": "OpenRouter 限流",
                "actions": ["等几分钟重试, 或升级 OpenRouter 套餐"],
            }
        else:
            result["llm_test"] = {
                "ok": False,
                "error_code": r.status_code,
                "error": r.text[:500],
                "actions": ["把这页发给开发者"],
            }
    except httpx.ConnectError as e:
        result["llm_test"] = {
            "ok": False,
            "error_code": -1,
            "error": f"连不上 OpenRouter: {e}",
            "diagnosis": "项目到 openrouter.ai 的网络不通 (可能是防火墙/代理/账号地区限制)",
            "actions": [
                "1. 在浏览器打开 https://openrouter.ai 看能不能访问",
                "2. 如果打不开 → 这是网络问题, 需要科学上网 / 换代理",
                "3. 如果能打开但项目连不上 → 检查 Windows 防火墙",
            ],
        }
    except Exception as e:
        result["llm_test"] = {
            "ok": False,
            "error": f"诊断失败: {e}",
            "actions": ["把这段错误发我"],
        }

    # v0.8.0: 3 档全量 ping - 在 API Key 下分别验证 low/mid/high 的 primary + fallback
    # 让诊断页能看到每个模型到底能不能调, 不只凭 "key 有误" 推断
    result["tier_routing"] = {
        "low": {
            "primary": settings.TIER_MODEL_LOW,
            "fallback": [m.strip() for m in (settings.TIER_FALLBACK_LOW or "").split(",") if m.strip()],
        },
        "medium": {
            "primary": settings.TIER_MODEL_MEDIUM,
            "fallback": [m.strip() for m in (settings.TIER_FALLBACK_MEDIUM or "").split(",") if m.strip()],
        },
        "high": {
            "primary": settings.TIER_MODEL_HIGH,
            "fallback": [m.strip() for m in (settings.TIER_FALLBACK_HIGH or "").split(",") if m.strip()],
        },
    }
    # high 档触发条件 (v0.8.0 用户 2026-07-28 规则)
    result["tier_routing"]["high_trigger_rule"] = (
        "high  = (深度思考 ON) AND (任务分类 = high)  → high\n"
        "       任何其他情况                             → 上限 mid\n"
        " 举例: 开深度思考 + 问高考志愿方案 = high, 开深度思考 + 问「你好」= mid (任务不够 complex)"
    )

    # 并行 ping 所有 tier 的 primary + fallback (节省总时间)
    import asyncio
    if settings.LLM_API_KEY:
        async def ping(model: str) -> dict:
            """ping 单个模型, 返回 {ok, status_code, latency_ms, tokens, model_returned, error}"""
            import time
            t0 = time.time()
            try:
                cr = await httpx.AsyncClient().post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.LLM_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": settings.OPENROUTER_REFERER,
                        "X-Title": settings.OPENROUTER_TITLE,
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 3,
                    },
                    timeout=10,
                )
                latency = int((time.time() - t0) * 1000)
                if cr.status_code == 200:
                    data = cr.json()
                    usage = data.get("usage", {})
                    return {
                        "ok": True,
                        "status_code": 200,
                        "latency_ms": latency,
                        "model_returned": data.get("model", model),
                        "tokens": usage.get("total_tokens", 0),
                        "cost": usage.get("cost", 0),
                    }
                else:
                    body = cr.text[:150]
                    return {
                        "ok": False,
                        "status_code": cr.status_code,
                        "latency_ms": latency,
                        "error": body,
                        "error_type": "region" if cr.status_code == 403 and "region" in body.lower() else
                                      "payment" if cr.status_code == 402 else
                                      "not_found" if cr.status_code == 404 else
                                      "unknown",
                    }
            except httpx.ConnectError as e:
                return {"ok": False, "error": f"网络不通: {str(e)[:80]}", "error_type": "network", "latency_ms": int((time.time() - t0) * 1000)}
            except Exception as e:
                return {"ok": False, "error": str(e)[:80], "error_type": "unknown", "latency_ms": int((time.time() - t0) * 1000)}

        # 收集所有模型 (去重保序)
        all_models = []
        seen_models = set()
        for tier_name in ("low", "medium", "high"):
            cfg = result["tier_routing"][tier_name]
            for role in ("primary", "fallback"):
                m = cfg.get(role, [])
                if isinstance(m, str):
                    m = [m]
                for model in m:
                    if model and model not in seen_models:
                        seen_models.add(model)
                        all_models.append(model)
        # 并行 ping
        ping_results = await asyncio.gather(*[ping(m) for m in all_models])
        result["api_call_status"] = {
            "pinged_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "models": dict(zip(all_models, ping_results)),
            "summary": {
                "total": len(ping_results),
                "ok": sum(1 for r in ping_results if r.get("ok")),
                "failed": sum(1 for r in ping_results if not r.get("ok")),
            },
        }
    else:
        result["api_call_status"] = {"error": "LLM_API_KEY 未设, 跳过 ping"}

    # 探测 high 档 primary (保留旧字段作向后兼容)
    if settings.TIER_MODEL_HIGH:
        try:
            cr = await httpx.AsyncClient().post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.LLM_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": settings.OPENROUTER_REFERER,
                    "X-Title": settings.OPENROUTER_TITLE,
                },
                json={
                    "model": settings.TIER_MODEL_HIGH,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
                timeout=15,
            )
            if cr.status_code == 200:
                result["high_tier_access"] = {
                    "ok": True,
                    "model": settings.TIER_MODEL_HIGH,
                    "message": f"✓ high 档 primary ({settings.TIER_MODEL_HIGH}) 可用",
                }
            elif cr.status_code == 403 and ("region" in cr.text.lower() or "not available" in cr.text.lower()):
                result["high_tier_access"] = {
                    "ok": False,
                    "model": settings.TIER_MODEL_HIGH,
                    "error": f"{settings.TIER_MODEL_HIGH} 被地区限制 (403 region)",
                    "impact": "high 档 primary 调不通, 会降级到 fallback 链",
                    "actions": [
                        f"1) 换可调 {settings.TIER_MODEL_HIGH} 的 key",
                        "2) 或把 .env 的 TIER_MODEL_HIGH 改成你 key 能调的 (z-ai/glm-5.2 / meta-llama/llama-4-maverick / mistralai/mistral-large-2407 等)",
                        "3) 或不处理, 接受自动降级",
                    ],
                }
            else:
                result["high_tier_access"] = {
                    "ok": False, "model": settings.TIER_MODEL_HIGH,
                    "error_code": cr.status_code, "error": cr.text[:200],
                }
        except Exception as ce:
            result["high_tier_access"] = {"ok": None, "error": f"探测失败: {ce}"}

    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
