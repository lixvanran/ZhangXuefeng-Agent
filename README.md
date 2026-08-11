# 张雪峰智能体 v0.9.1

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

## v0.9.1 升级要点

> **v0.9.1 重构了路由架构 + 加了启动自检和前端诊断页**

- **架构重构**：路由逻辑从 `app/agent/pipeline/complexity.py` + `app/agent/llm/router.py` 合并到新的 `app/agent/routing/` 模块
  - `classifier.py` — `ComplexityClassifier` Protocol + 3 个实现 (MiniMaxM3 / Heuristic / Ensemble)
  - `tier_router.py` — `TierRouter` 类，3 档配置 + `classify_and_route()` 一步到位
  - 未来加新分类器/路由器只需实现接口, 不动 orchestrator
- **minimaxM3 复杂度分类**：默认用 `minimax/minimax-m3` 评估问题复杂度，失败自动降级到启发式
- **启动自检**：启动时自动 ping OpenRouter 验证 key，401 立刻在日志里给诊断
- **前端诊断页**：左侧导航"系统诊断" → 一键检测 key 状态，按步骤给解决方案
- **三档路由**：闲聊走 Qwen 7B，标准问答走 Sonnet，复杂规划也走 Sonnet（Opus 太贵）
- **TTS 修复**：之前完全跑不起来，现已接好 MiniMax TTS，配上 `MINIMAX_API_KEY` 就能用；不配也不影响聊天
- **Embedding 二选一**：无 key → 本地 TF-IDF；配 `OPENAI_API_KEY` → 真语义 embedding
- **数据库迁移安全化**：之前缺列会 DROP 整张表清空数据，现在 ALTER TABLE 补列
- **加 .gitignore**：之前的版本没 .gitignore，API key 一推就裸奔
- **force_tier 调试开关**：默认禁用，避免客户端乱指定模型打爆月费

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
│   │   │   │   └── tier_router.py  - 档位路由器
│   │   │   ├── llm/              - LLM 客户端 (base / openrouter / deep_thinking / vision)
│   │   │   ├── rag/              - RAG 检索
│   │   │   ├── memory/           - 会话/记忆
│   │   │   ├── pipeline/          - 消息处理管道
│   │   │   ├── prompts/           - System prompt 拼装
│   │   │   ├── search/            - 联网搜索
│   │   │   ├── tools/             - 工具 (查大学/专业/政策/搜索)
│   │   │   └── orchestrator.py    - 总编排
│   │   ├── routers/      - API 路由 (chat / resources / conversations / user / tts)
│   │   ├── services/     - 业务服务
│   │   └── core/         - 配置 / 模型
│   ├── knowledge_base/   - 知识库 (11 文件, 200+ 项)
│   └── requirements.txt
├── frontend/             - 前端代码 (React + Vite + Tailwind)
│   └── src/
│       ├── pages/        - 页面 (Chat / Resources / Profile)
│       ├── components/   - 组件 (DiagnoseModal - 系统诊断)
│       ├── api/          - API 客户端
│       └── store/        - Zustand 状态
├── scripts/              - 声纹克隆辅助脚本 (可选)
│   ├── clone_zhang_voice.py
│   ├── download_zhang_audio.py
│   └── generate_demo_voice.py
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

