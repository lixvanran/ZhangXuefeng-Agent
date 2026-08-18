# 张雪峰智能体 v0.9.8

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

## v0.9.8 升级要点

> **v0.9.8 — 1 key 跑全部 + KB 集成 2 个开源 repo (124 篇高质量内容)**

- **1 个 key 跑全部**：之前 3 个 key (LLM/MINIMAX/OPENAI) 现在合并成 1 个 `LLM_API_KEY` (走 OpenRouter)
  - LLM (主对话/路由/Vision) — OpenRouter ✅
  - Embedding — OpenRouter 调 `openai/text-embedding-3-small` ✅
  - Deep thinking — 共用 LLM key ✅
  - TTS — 改**浏览器 Web Speech API**，0 key 0 成本 ✅
  - 搜索 — DuckDuckGo 兜底 0 key ✅
  - 用户只需要配 1 个 `LLM_API_KEY` (OpenRouter 的)
  - 其他 key (MINIMAX_API_KEY / OPENAI_API_KEY / TAVILY_API_KEY) 保留为向后兼容占位
- **KB 大幅扩充**：集成 2 个 License 明确的公开 KB（**124 篇**高质量内容，**178.8 KB**）
  - **Eric-Yibo-Shen/zhangxuefeng-skillset** (CC BY 4.0): 8 个核心知识模块
    - AI 时代专业选择动态校正 (2026-2030 视角)
    - 专业选择决策框架 (高确定性 vs 高风险)
    - 志愿填报操作框架 (冲稳保/城市优先级)
    - 就业路径分析 (五条主路径真实评估)
    - 院校选择参考框架 (各分数段逻辑)
    - 备考策略与决策底层逻辑
    - 大学在校阶段规划
    - 新高考选科决策 (3+1+2 模式, 物理 vs 历史)
  - **zouchenzhen/zhangxuefeng-skill-star** (MIT): 6 份深度研究
    - 著作与系统思考 (5 本书核心)
    - 深度采访与对谈 (15+ 权威媒体)
    - 表达风格 DNA (5 个心智模型 + 8 条决策启发式)
    - 他者视角与批评
    - 重大决策分析 (11 个关键决策)
- **新 KB 文件**：`backend/knowledge_base/10_external_kb.json`
  - RAG 自动发现加载（无需改代码）
  - 每条带 `source` (哪个 repo) + `license` (CC BY 4.0 / MIT) 元数据
  - 按 ## 切分, 长段自动切, 共 **124 个 entries**
  - 覆盖: AI 时代 / 专业 / 志愿 / 就业 / 院校 / 选科 / 学习方法 / 大学规划 / 著作 / 对话 / 表达 / 评价 / 决策

## v0.9.7 升级要点

> **v0.9.7 重大修复 — 错题卡死的真凶 + OpenRouter 开销爆表的真凶 + 错题本图片显示真凶 + 错题整理效率优化**

- **错题本卡死修复**：`tier_router.py` 之前**缩进错**导致 `classify_and_route` 不在 `class TierRouter` 内
  - 症状：发消息后卡死 → 报 `AttributeError: 'TierRouter' object has no attribute 'classify_and_route'`
  - 根因：v0.9.4 重构时 `_load_tiers_from_db` 缩进 0 把 class 提前结束，后面所有方法都被 Python 忽略
  - 修复：彻底重写 `tier_router.py`，所有方法正确缩进在 class 内（验证 7 个方法都在）
- **OpenRouter 开销爆表修复**：`/api/diagnose` 之前**每次打开并行 ping 6 个模型**（3 档 × primary + fallback）
  - 症状：OpenRouter 后台看到一堆 "other" 模型调用 + 当日开销明显大于平时
  - 根因：ping 逻辑会真调 OpenRouter `chat/completions`（虽然 max_tokens=3 很小，但 6 次累积就是 6 次 overhead + 6 条记录）
  - 修复：diagnose 改为**只展示配置，不自动 ping**（要测点"重新检测"按钮手动触发）
- **启动时不主动探测 high 档**：删 `self_check_anthropic_access` 和 `_probe_high_tier_access`（启动也消耗 token）
- **DB 读时序修复**：`tier_router.__init__` 不再立即读 DB（避免 import 时 DB 还没建好的报错），延迟到第一次 `classify_and_route` 调用
- **LLM 幻觉 `read_file` 工具修复**
  - 症状：你上传图片后说"整理错题"，LLM 调 `read_file`（不存在）→ 报"Unknown tool" → 卡死
  - 根因：Claude/GPT 训练数据里"读文件"的标准工具名是 `read_file`，LLM 看到 uploads 目录就**强烈倾向**调这个名
  - 修复：
    1. **加 `read_file` 工具**（LLM 调它就路由到 `workspace_read`）
    2. **`workspace_read` 增强**：uploads/ 下的图片**自动走 Vision 识别**
    3. **传 `path="uploads"`**：智能列出 uploads 目录所有待处理文件
- **错题本图片显示修复**
  - 症状：错题本里 M-001 这类看不到原图，要么空、要么 404
  - 根因 1：wrong_book 存的是 Windows 绝对路径 (`D:\xxx\uploads\xxx.png`)，浏览器访问 `file:///` 失败
  - 根因 2：`/uploads` 静态服务只 mount 了 `backend/data/uploads/`，**没 mount `workspace/uploads/`** —— 你上传的图片实际放 workspace/uploads
  - 根因 3：Agent 调 `wrong_book_add_mistake` 不传 file_path
  - 修复：
    1. **wrong_book 改存相对路径**（`uploads/xxx.png`）
    2. **main.py 把 `/uploads` 挂到 `workspace/uploads/`**（老路径 `/legacy-uploads` 保留）
    3. **resources._serialize 把 file_path 转成 web URL**（绝对/相对都兼容）
    4. **prompt + 工具描述双重强调 file_path 必传**，设为 required
- **错题整理 3 次才成的效率优化**（最大改进）
  - 症状：你说"整理错题"后，Agent 调完 `describe_file` 拿到图片描述，**就只用 markdown "整理好了"**，没真写入错题本。要你说第 2 遍"帮我整理上去"才调 `add_mistake`
  - **根因（找到了）**：`llm_runner.py` 第二次 LLM 调用 `tools=[]`（空）！意思是 LLM 拿到工具结果后**不能再调工具**，只能文字回答
  - 修复：
    1. **多轮工具循环**：最多 3 轮（scan → describe → add_mistake 正好 3 步）
    2. **每轮都带 tools**：LLM 看到 describe_file 结果后能继续调 add_mistake
    3. **最后不带 tools**：强制出 markdown 答案给用户看
  - **效果**：你说 1 次"整理错题"，Agent 自动跑完 3 步工具链 + 1 段总结，不用你说第 2 遍

## v0.9.4 升级要点

> **v0.9.4 bugfix — 修 2 个用户反馈的真 bug：API 状态显示的模型还是旧值 + 错题本 Agent 调错工具**

- **API 状态显示修复**：`/api/diagnose` 之前读 `settings.TIER_MODEL_*`（来自 .env），不读 DB
  - 即使你在系统设置里改了模型，**API 状态页还显示 .env 旧值**（让你以为没生效）
  - v0.9.4 修：API 状态页也读 `user_preferences` 表，跟 tier_router 行为一致
- **错题本 prompt 强化**：
  - v0.9.3 时 Agent 偶尔会**幻觉调用**不存在的工具（如 `read_resource`）
  - v0.9.4 修：exam.py prompt 强制"必须按顺序调 wrong_book_* 三个工具，不要调其他工具"

## v0.9.3 升级要点

> **v0.9.3 bugfix — 修 2 个用户反馈的真 bug：错题本乱码 + 自定义模型不生效**

- **错题本工作流修复**：vision 模型 fallback 删掉 `minimax/minimax-01`（该模型在 OpenRouter 上**根本不存在**，调它会返回乱码 → 张老师生成"乱码回复"）
  - 主选: `z-ai/glm-4.5v`（国产便宜中文强）
  - fallback: `qwen/qwen2.5-vl-72b-instruct` / `meta-llama/llama-4-scout` / `google/gemini-2.5-flash`
- **自定义模型真的生效了**：
  - v0.9.2 时 tier_router 用单例模式，启动时读一次 DB 就再也不读，**改设置后永远不生效**
  - v0.9.3 修：每次 `classify_and_route` 之前都重新读 `user_preferences` 表（DB 读是轻量 key-value lookup，性能影响可忽略）
  - 现在在系统设置里改 low/mid/high 档模型 → 下一个对话立刻生效

## v0.9.2 升级要点

> **v0.9.2 bugfix — 修 3 个关键 bug，让 v0.9.1 功能真正跑起来**
>- **后端启动崩溃修复**：
  - `database.py` 加 `import logging` + `logger = logging.getLogger(__name__)`（之前整个文件没定义 logger，调用就崩）
  - `main.py` 别名 import `settings as settings_router`，避免覆盖 `app.core.config.settings` Pydantic 实例
  - `main.py` 显式 `import UserPreferenceORM`，确保 `Base.metadata` 注册后 `create_all` 才建表
- **`user_preferences` 表兜底创建**：老数据库升级时如果缺这个表，`_migrate_if_needed` 用 SQL `CREATE TABLE` 强建（双保险）
- **前端 API 路径去重**：`/api/api/...` → `/api/...`（axios `baseURL: '/api'` 已经带前缀了，不要再加）
- **`.gitignore` 修复**：`uploads/` 误伤 `workspace/uploads/`，删掉这条规则（`backend/data/uploads/` 已精确匹配）

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

## 错题本工作流 (v0.9.5)

1. 把错题图片/PDF/Word/文本**拖到** `workspace/uploads/`（或用 Chat 页面 📎 上传）
2. 在 Chat 里说 **"把上传文件夹里的错题整理一下"**
3. Agent 自动扫描 → Vision 识别内容 → 提取学科/知识点/错误类型 → 写入错题本（自动 M-001 编号 + RAG 索引）
4. 之后问"我错过的圆锥曲线题"会引用到错题本

## 系统设置 (v0.9.5)

左侧导航"系统设置"（原"系统诊断"），3 个 tab：
- **API 状态** — 检测 OpenRouter key 有效性 + 显示三档模型配置
- **模型设置** — 选 low/mid/high 档模型（严格白名单）
- **消费/余额** — OpenRouter 账号余额/已用/剩余 + 进度条

## high 模式 (v0.9.5)

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
