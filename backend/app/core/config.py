"""Application configuration"""
import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Optional


# Force .env to take priority over system env vars
def _load_env_files():
    base = Path(__file__).resolve().parent.parent.parent
    project_root = base.parent
    for fp in [project_root / ".env", base / ".env"]:
        if fp.exists():
            load_dotenv(fp, override=True, encoding="utf-8")

_load_env_files()


class Settings(BaseSettings):
    """App settings"""

    # App
    APP_NAME: str = "ZhangXueFeng Agent"
    APP_VERSION: str = "0.9.7"  # v0.9.7: 多轮工具循环 + 错题本图片修复 + read_file 工具 stub
    DEBUG: bool = True

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = ["*"]

    # ===== LLM (Chat) =====
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"
    # 默认用国产便宜模型; 用户可在 .env 改成 Claude / GPT-4o
    LLM_MODEL: str = "qwen/qwen-2.5-72b-instruct"
    LLM_FALLBACK_MODELS: str = "deepseek/deepseek-chat,qwen/qwen-2.5-7b-instruct"

    # Feature toggles (true/false) — set in .env
    WEB_SEARCH_ENABLED: bool = True  # v0.7.9.3: web search re-enabled (Tavily primary, fetch_url for full text) (use KB instead)
    DEEP_THINKING_ENABLED: bool = False

    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 3000  # v0.8.0: 提高到 3000, GLM 5.x 默认带 reasoning, 需要额外 token 空间

    # ===== 多 provider 直连 (可选, 默认走 OpenRouter 统一入口) =====
    # 直连 Claude 用 ANTHROPIC_API_KEY, 直连 GLM 用 GLM_API_KEY
    # 当前实现里这两个 key 只在 settings 里占位, 没被代码用上
    # (统一走 OpenRouter, 用户配 ANTHROPIC_API_KEY 反而易混)
    # 保留字段, 后续若需要直连再启用
    GLM_API_KEY: str = ""
    GLM_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    GLM_MODEL: str = "glm-4-plus"

    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"
    ANTHROPIC_MODEL_OPUS: str = "claude-opus-4-20250514"
    ANTHROPIC_MODEL_SONNET: str = "claude-sonnet-4-20250514"
    ANTHROPIC_MODEL_DEFAULT: str = "claude-sonnet-4-20250514"

    # ===== Deep Thinking Model =====
    # 用 DeepSeek R1 (带 reasoning_content 字段), 走 OpenRouter
    DEEP_THINKING_MODEL: str = "deepseek/deepseek-r1"
    DEEP_THINKING_BASE_URL: str = ""  # if empty, use LLM_BASE_URL
    DEEP_THINKING_API_KEY: str = ""  # if empty, use LLM_API_KEY
    DEEP_THINKING_EFFORT: str = "medium"  # low/medium/max (DeepSeek 风格)
    DEEP_THINKING_FALLBACK_MODELS: str = "deepseek/deepseek-chat,qwen/qwen-2.5-72b-instruct"

    # ===== v0.8.0: Model Tier Routing (用户指定 2026-07-28) =====
    # primary 严格按用户指定: low=MiniMax M3, mid=Z.ai GLM 5.2, high=Grok 4.20 Multi-Agent
    # fallback 走便宜/能力强/同档位替代
    # - low    (闲聊/简单): MiniMax M3 — 轻量便宜中文强
    # - medium (标准问答): Z.ai GLM 5.2 — 国产强
    # - high   (复杂规划): Grok 4.20 Multi-Agent (xAI 最新旗舰, 多智能体协作)
    # 实测 2026-07-28: 这个 OpenRouter 账号调不通 OpenAI / Anthropic / Google / Llama 4
    #   (全 region 限), 但能调 xAI Grok 全系列 (用户 2026-07-28 改用 Grok 4.20 MA)
    # HIGH 档触发条件 (用户规则 2026-07-28): 手动开深度思考 AND 任务分类为 high → high
    #   缺一不可: 没开深度思考 → 最多 mid
    TIER_MODEL_LOW: str = "minimax/minimax-m3"
    TIER_FALLBACK_LOW: str = "minimax/minimax-m2.7,z-ai/glm-4.5-air,deepseek/deepseek-chat-v3.1"
    TIER_MODEL_MEDIUM: str = "z-ai/glm-5.2"
    TIER_FALLBACK_MEDIUM: str = "minimax/minimax-m2.7,z-ai/glm-5-turbo,deepseek/deepseek-chat-v3.1"
    TIER_MODEL_HIGH: str = "x-ai/grok-4.20-multi-agent"
    TIER_FALLBACK_HIGH: str = "x-ai/grok-4.20,x-ai/grok-4.5,z-ai/glm-5.2,z-ai/glm-5-turbo,minimax/minimax-m2.7,deepseek/deepseek-chat-v3.1"
    # 分类用模型 (默认用 low 档, 越便宜越好)
    TIER_CLASSIFY_MODEL: str = "minimax/minimax-m3"
    # 复杂度分类专用模型 — 用 minimaxM3 (轻量便宜中文强, 适合分类)
    # 在 OpenRouter 上的模型名: 默认为 minimax/minimax-m3, 如果你账号里叫别的改这里
    CLASSIFY_MODEL: str = "minimax/minimax-m3"

    # ===== Vision Model (for image description) =====
    # v0.9.5: 修 vision fallback — 删掉 minimax/minimax-01 (该模型在 OpenRouter 上不存在, 会返回乱码)
    # 实测能调的多模态: z-ai/glm-4.5v (国产便宜中文强) + fallback qwen2.5-vl-72b / llama-4-scout / gemini-2.5-flash
    VISION_MODEL: str = "z-ai/glm-4.5v"
    VISION_BASE_URL: str = ""  # if empty, use LLM_BASE_URL
    VISION_API_KEY: str = ""  # if empty, use LLM_API_KEY
    VISION_FALLBACK_MODELS: str = "qwen/qwen2.5-vl-72b-instruct,meta-llama/llama-4-scout,google/gemini-2.5-flash"

    # ===== Embedding =====
    # If OPENAI_API_KEY is set, use OpenAI; otherwise use local sentence-transformers
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ===== Web Search =====
    # Tavily is preferred (1000 free/month). If empty, use DuckDuckGo
    TAVILY_API_KEY: str = ""

    # ===== MiniMax TTS (optional, 不配也能用聊天, 只朗读功能用) =====
    # 注册: https://platform.MiniMax.io → 充值 → 创建 API Key
    # 不填 → 朗读按钮返回 503 友好提示, 不影响聊天/资料
    MINIMAX_API_KEY: str = ""
    MINIMAX_BASE_URL: str = "https://api.minimax.chat/v1"
    MINIMAX_TTS_MODEL: str = "speech-2.8-turbo"  # 可选 speech-2.8-hd (更高清)
    MINIMAX_VOICE_DEFAULT: str = "male-qn-qingse"

    # ===== v0.7.9.4: Voice Cloning (optional) =====
    # 如果用 MiniMax clone_voice 克隆了张雪峰声音, 把 voice_id 填这里
    # 流程: 1) samples/zhangxuefeng.mp3 准备好  2) python scripts/clone_zhang_voice.py
    #      3) 脚本会自动写到这里
    ZHANG_VOICE_ID: str = ""

    # ===== HuggingFace Mirror =====
    HF_ENDPOINT: str = "https://hf-mirror.com"

    # ===== OpenRouter (optional) =====
    OPENROUTER_REFERER: str = "http://localhost:3000"
    OPENROUTER_TITLE: str = "ZhangXueFeng-Agent"

    # ===== Paths =====
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    PROJECT_ROOT: Path = BASE_DIR.parent  # 项目主目录 (zhangxuefeng-demo/)
    DATA_DIR: Path = BASE_DIR / "data"
    KNOWLEDGE_BASE_DIR: Path = BASE_DIR / "knowledge_base"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    CHROMA_DIR: Path = DATA_DIR / "chroma"
    SQLITE_PATH: Path = DATA_DIR / "sqlite.db"
    # v0.8.0: Agent 工作文件夹 (主目录下), 用户/agent 都能读写
    WORKSPACE_DIR: Path = PROJECT_ROOT / "workspace"
    # v0.9.1: workspace/uploads/ — 用户把错题图片/PDF/Word 等放在这里
    # Agent 通过 chat 指令自动扫描 → 识别 → 归类到错题本
    WORKSPACE_UPLOADS_DIR: Path = WORKSPACE_DIR / "uploads"

    # ===== Database =====
    DATABASE_URL: str = f"sqlite:///{SQLITE_PATH}"

    # ===== Computed properties =====
    @property
    def is_openrouter(self) -> bool:
        return "openrouter.ai" in self.LLM_BASE_URL

    @property
    def embedding_provider(self) -> str:
        """openai or local"""
        if self.OPENAI_API_KEY:
            return "openai"
        return "local"

    @property
    def search_provider(self) -> str:
        """tavily or duckduckgo"""
        if self.TAVILY_API_KEY:
            return "tavily"
        return "duckduckgo"

    class Config:
        # BASE_DIR is the directory containing this config.py's parent
        # config.py: backend/app/core/config.py -> 3 levels up = backend/
        # Project root: 4 levels up
        _base_dir = Path(__file__).resolve().parent.parent.parent
        env_file = [
            str(_base_dir.parent / ".env"),  # project root .env
            str(_base_dir / ".env"),          # backend/.env
            ".env",
        ]
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.WORKSPACE_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
settings.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
# v0.8.0: 创建工作文件夹 (主目录下)
settings.WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
# 写一个 README 让用户知道这文件夹干嘛的
_workspace_readme = settings.WORKSPACE_DIR / "README.md"
if not _workspace_readme.exists():
    _workspace_readme.write_text(
        "# Agent 工作文件夹\n\n"
        "这是张老师 (agent) 能读写的文件夹, 你也可以手动放文件进去。\n\n"
        "## 能干啥\n\n"
        "- agent 可以列出 / 读 / 写 / 搜索这里的文件\n"
        "- 你可以手动放文件 (笔记、题目、资料) 让 agent 帮你整理\n"
        "- agent 也可以把搜索结果 / 计算过程 / 答案写到这\n\n"
        "## 工具\n\n"
        "- `workspace_list` - 列出文件\n"
        "- `workspace_read` - 读文件\n"
        "- `workspace_write` - 写文件 (覆盖)\n"
        "- `workspace_append` - 追加\n"
        "- `workspace_search` - 搜文件内容\n"
        "- `workspace_delete` - 删文件\n\n"
        "## 建议用法\n\n"
        "```\nworkspace/\n"
        "├── 错题本/             # 你的错题照片/笔记\n"
        "│   ├── 数学-圆.md\n"
        "│   └── 物理-力学.md\n"
        "├── 笔记/               # 你的学习笔记\n"
        "├── 资料/               # agent 搜到的资料\n"
        "└── 计划/               # agent 给你做的规划\n"
        "```\n",
        encoding="utf-8"
    )
