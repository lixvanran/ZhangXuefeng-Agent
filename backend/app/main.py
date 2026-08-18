"""FastAPI main"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.core.config import settings
from app.db.database import init_db
# v0.9.1: 修复 — 显式 import 所有 ORM 类, 确保 Base.metadata 里有它们
# (否则 create_all 不会建新表 — 出现 "no such table: user_preferences" 错误)
from app.db.database import UserPreferenceORM  # noqa: F401
from app.routers import chat, resources, conversations, user, tts, workspace
# v0.9.1: 修复 — 别名 import 避免覆盖 app.core.config.settings
from app.routers import settings as settings_router
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

    # TTS — v0.9.8: 浏览器 Web Speech API, 0 key 0 成本
    logger.info("TTS: browser Web Speech API (v0.9.8 改用浏览器原生, 无需 key)")

    # Routing
    from app.agent.routing import get_tier_router, get_classifier
    router = get_tier_router()
    logger.info(f"Routing: classifier ready, tiers configured")

    # ★ 启动自检: ping 一下 OpenRouter 验证 key 是否有效
    # 不通过也不报错, 只在日志里告警
    await self_check_openrouter()

    # v0.9.5: 删 self_check_anthropic_access (启动时不再主动 ping 模型, 避免 OpenRouter 开销)
    # 如果要看模型能不能调, 点 API 状态页的"重新检测"按钮

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


# v0.9.5: 删 self_check_anthropic_access 和 _probe_high_tier_access
# 这两个函数启动时多调一次 OpenRouter chat/completions (消耗 token)
# 而且你 OpenRouter 上看到的 "other" 模型和开销爆表, 大概率就是这些
# 改: 不再启动时主动 ping, 用户想测可点 API 状态页的"重新检测"


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

# v0.9.6: 把 /uploads 挂到 workspace/uploads/ — 错题本实际存放位置
# 之前挂到 backend/data/uploads/ 是错的, 用户上传的图片不在那
app.mount("/uploads", StaticFiles(directory=str(settings.WORKSPACE_UPLOADS_DIR)), name="uploads")
# 老路径兼容: backend/data/uploads/ 里可能还有老用户的数据
app.mount("/legacy-uploads", StaticFiles(directory=str(settings.UPLOAD_DIR)), name="legacy_uploads")

app.include_router(chat.router)
app.include_router(resources.router)
app.include_router(conversations.router)
app.include_router(user.router)
app.include_router(tts.router)
app.include_router(workspace.router)
app.include_router(settings_router.router)


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
        "tts_enabled": True  # v0.9.8: browser web speech always available,
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
        "tts_enabled": True  # v0.9.8: browser web speech always available,
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
    # v0.9.5: 修 — 之前读 settings.TIER_MODEL_* (.env), 不读 DB
    # 用户在前端"系统设置"改了, 这里仍显示 .env 旧值
    from app.agent.routing.tier_router import TierRouter
    current_routing = TierRouter.get_current_routing()
    result["tier_routing"] = {
        "low": {
            "primary": current_routing["low"].primary,
            "fallback": current_routing["low"].fallback,
        },
        "medium": {
            "primary": current_routing["medium"].primary,
            "fallback": current_routing["medium"].fallback,
        },
        "high": {
            "primary": current_routing["high"].primary,
            "fallback": current_routing["high"].fallback,
        },
    }
    # high 档触发条件 (v0.8.0 用户 2026-07-28 规则)
    result["tier_routing"]["high_trigger_rule"] = (
        "high  = (深度思考 ON) AND (任务分类 = high)  → high\n"
        "       任何其他情况                             → 上限 mid\n"
        " 举例: 开深度思考 + 问高考志愿方案 = high, 开深度思考 + 问「你好」= mid (任务不够 complex)"
    )

    # v0.9.5: 修高开销 bug — 之前 diagnose 每次打开都并行 ping 6 个模型 (3 档 × primary + fallback)
    # 每个 ping 调 OpenRouter chat/completions (虽然 max_tokens=3 很小, 但 6 次 = 6 次 overhead)
    # 用户 OpenRouter 上看到 "other" 模型 + 开销爆表, 大概率就是这些 ping 累积
    # 现在改成: 只展示配置, 不自动 ping. 如果要看模型能不能调, 用户点重新检测按钮再 ping
    result["api_call_status"] = {
        "note": "v0.9.5: 改成不自动 ping (避免 OpenRouter 开销), 想测可点 API 状态页的重新检测按钮",
        "models": {},
        "summary": {"total": 0, "ok": 0, "failed": 0},
    }

    # 探测 high 档 primary (保留旧字段作向后兼容) - v0.9.5: 同样不自动 ping
    result["high_tier_access"] = {
        "note": "v0.9.5: 改成不自动 ping, 想测可点重新检测按钮"
    }

    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
