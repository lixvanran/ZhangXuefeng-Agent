# 张雪峰智能体 v0.9.2

> 敢说真话的 AI 备考与志愿填报助手

## 三个文件搞定一切

```
启动.bat   ← 双击启动
停止.bat   ← 双击停止
诊断.bat   ← 出问题用
```

## 怎么用

1. **解压**到任意目录
2. **双击 `启动.bat`**
3. 第一次会装依赖（5-10 分钟）
4. 浏览器自动打开 http://localhost:3000
5. 跟张雪峰老师聊天

要停止服务，**双击 `停止.bat`**。

## v0.9.2 修复要点

> **v0.9.2 bugfix 版本 — 修 3 个关键 bug, 让 v0.9.2 功能真正跑起来**

- **后端启动崩溃修复**：
  - `database.py` 加 `import logging` + `logger = logging.getLogger(__name__)`（之前整个文件没定义 logger，调用就崩）
  - `main.py` 别名 import `settings as settings_router`，避免覆盖 `app.core.config.settings` Pydantic 实例
  - `main.py` 显式 `import UserPreferenceORM`，确保 `Base.metadata` 注册后 `create_all` 才建表
- **`user_preferences` 表兜底创建**：老数据库升级时如果缺这个表，`_migrate_if_needed` 用 SQL `CREATE TABLE` 强建（双保险）
- **前端 API 路径去重**：`/api/api/...` → `/api/...`（axios `baseURL: '/api'` 已经带前缀了，不要再加）
- **`.gitignore` 修复**：`uploads/` 误伤 `workspace/uploads/`，删掉这条规则（`backend/data/uploads/` 已精确匹配）
- **App.tsx / config.py / README** 版本号统一对齐 v0.9.2

## v0.9.2 升级要点

> **v0.9.2 错题本工作流优化 + 切场景不再建新对话 + 系统设置 + 用户可选模型**

- **错题本工作流优化**：
  - 新增 `workspace/uploads/` 目录 — 把错题图片/PDF/Word 直接拖进去
  - Chat 页面加 📎 上传按钮（支持多选 + 进度条）
  - 新增 Agent 工具 `wrong_book_*`（扫描/识别/归类/查询），对话里说"把上传文件夹里的错题整理一下"即可自动入库
  - 错题本用现有 M-001 编号体系 + RAG 索引（无需重建）
- **修切场景 bug**：之前点场景会建新对话，现在只有点"新对话"按钮才建
- **系统诊断 → 系统设置**：3 个 tab — API 状态 / 模型设置 / 消费余额
- **模型可配置**（前端可选，**严格白名单**）：
  - 默认: low=minimaxM2.7, mid/high=minimaxM3
  - low 可选: qwen-2.5-7b / minimaxM2.7 / deepseek-v3.1
  - mid 可选: minimaxM3 / glm-5 / deepseek-v4-flash
  - high 可选: minimaxM3 / grok-4.20-multi-agent / glm-5.2 / deepseek-v4-pro
  - 触发规则: high 档 = 分类=high **且** 开启 "high 模式"（原"深度思考"按钮改名）
  - 配置存在 `user_preferences` 表，重启生效
- **余额查询**：调 OpenRouter `/api/v1/auth/key`（不消耗 token），显示邮箱/总额/已用/剩余/进度条
- **架构**：
  - `model_whitelist.py` — 严格白名单 + 默认值 + 兜底校验
  - `tier_router.py` 改从 DB 用户偏好读，env 仅作兜底
  - `UserPreferenceORM` 新表（key-value）
  - DiagnoseModal → SettingsModal

## 改 API Key

编辑 `.env` 文件，**至少需要配置**：

```bash
# 必填: OpenRouter (LLM 聊天)
LLM_API_KEY=sk-or-v1-xxx

# 选填: 朗读功能 (MiniMax TTS)
MINIMAX_API_KEY=xxx

# 选填: 更好的 RAG 语义召回 (OpenAI Embedding)
OPENAI_API_KEY=xxx
```

改完保存，**重启 `启动.bat`** 生效。

## 错题本工作流 (v0.9.2)

1. 把错题图片/PDF/Word/文本**拖到** `workspace/uploads/`（或用 Chat 页面 📎 上传）
2. 在 Chat 里说 **"把上传文件夹里的错题整理一下"**
3. Agent 自动扫描 → Vision 识别内容 → 提取学科/知识点/错误类型 → 写入错题本（自动 M-001 编号 + RAG 索引）
4. 之后问"我错过的圆锥曲线题"会引用到错题本

## 系统设置 (v0.9.2)

左侧导航"系统设置"（原"系统诊断"），3 个 tab：
- **API 状态** — 检测 OpenRouter key 有效性 + 显示三档模型配置
- **模型设置** — 选 low/mid/high 档模型（严格白名单）
- **消费/余额** — OpenRouter 账号余额/已用/剩余 + 进度条

## high 模式 (v0.9.2)

Chat 顶栏开关（原"深度思考"，改名"high 模式"）。开启后：
- 自动分类为 high 的请求 → 调用 high 档模型
- 关闭时：所有请求最多到 mid 档
- 调用规则: high = 分类=high **且** high 模式=开

## 出问题？

**双击 `诊断.bat`**，把生成的 `diagnose.txt` 发给我。

## 目录结构

```
zhangxuefeng-demo/
├── 启动.bat              ⭐ 双击启动
├── 停止.bat              ⭐ 双击停止
├── 诊断.bat              ⭐ 出问题用
├── .gitignore            - Git 忽略 (.env, data/, node_modules/ 等)
├── README.md             - 本文件
├── .env                  - API Key 配置 (OpenRouter)
├── .env.example          - 配置模板
├── backend/              - 后端代码
│   ├── app/
│   │   ├── agent/
│   │   │   ├── routing/           ⭐ 路由模块 (v0.8 新增)
│   │   │   │   ├── classifier.py   - 复杂度分类器 (MiniMaxM3 + Heuristic + Ensemble)
│   │   │   │   ├── tier_router.py  - 档位路由器 (v0.9.1 读用户偏好)
│   │   │   │   └── model_whitelist.py  ⭐ v0.9.2 新增 - 严格白名单
│   │   │   ├── llm/              - LLM 客户端 (base / openrouter / deep_thinking / vision)
│   │   │   ├── rag/              - RAG 检索
│   │   │   ├── memory/           - 会话/记忆
│   │   │   ├── pipeline/          - 消息处理管道
│   │   │   ├── prompts/           - System prompt 拼装
│   │   │   ├── search/            - 联网搜索
│   │   │   ├── tools/             - 工具 (含错题本 v0.9.1 新增 wrong_book.py)
│   │   │   └── orchestrator.py    - 总编排
│   │   ├── routers/      - API 路由 (chat / resources / conversations / user / tts / workspace / settings)
│   │   ├── services/     - 业务服务
│   │   └── core/         - 配置 / 模型
│   ├── knowledge_base/   - 知识库 (11 文件, 200+ 项)
│   └── requirements.txt
├── frontend/             - 前端代码 (React + Vite + Tailwind)
│   └── src/
│       ├── pages/        - 页面 (Chat / Resources / Profile)
│       ├── components/   - 组件 (SettingsModal - 系统设置 v0.9.1 替代 DiagnoseModal)
│       ├── api/          - API 客户端 (v0.9.1 +workspace.ts)
│       └── store/        - Zustand 状态 (v0.9.1 修切场景 bug)
├── scripts/              - 声纹克隆辅助脚本 (可选)
│   ├── clone_zhang_voice.py
│   ├── download_zhang_audio.py
│   └── generate_demo_voice.py
├── workspace/            - Agent 工作目录 (v0.8 新增)
│   ├── README.md
│   ├── uploads/          - ⭐ v0.9.2 新增 - 错题上传文件夹
│   └── ...               - 你的笔记/资料
└── samples/              - 音频样本位置 (可选)
```

## 知识库清单 (200+ 项 / 11 文件)

| 文件 | 项数 | 内容 |
|------|------|------|
| admission.json | 5 | 5 省 2024 录取数据 |
| colleges.json | 30 | 985/211 高校 |
| majors.json | 34 | 热门专业点评 |
| strategy.json | 8 | 报考策略 |
| life_kb.json | 25 | 人生规划 |
| policy.json | 10 | 高考政策 |
| cities.json | 10 | 城市选择 |
| career.json | 10 | 就业去向 |
| zhang_quotes.json | 30 | 张老师经典语录 |
| zhang_strategy_2026.json | 7 | 2026 备考理念 |
| gaokao_2026.json | 31 | 31 省 2026 分数线 |
