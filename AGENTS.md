# AGENTS.md

给后续维护这个仓库的人(和 agent)看的约定。
**背景说明与详细排查过程见 README 的 v0.10.0 章节。**

---

## 1. 这个项目是什么

张雪峰风格的 AI 备考与志愿填报助手。目标用户是**零技术的高考家庭**,
所以任何改动都要先问一句:**普通用户能不能自己装起来并用下去?**

- 后端: FastAPI, `backend/app/`
- 前端: Vite + React + TypeScript, `frontend/`
- 分发: `启动.bat` / `停止.bat` / `诊断.bat`(Windows 优先)
- 配置: **只需 1 个 `LLM_API_KEY`**(OpenRouter),其余全部有零 key 兜底

---

## 2. 环境事实(踩过的坑,别再踩)

| 事实 | 后果 |
|---|---|
| `config.py` 先加载根 `.env`,再加载 `backend/.env`,且 `override=True` | **`backend/.env` 胜出** → `backend/.env.example` 才是权威模板,根目录那份是历史遗留 |
| `TIER_MODEL_*` / `TIER_FALLBACK_*` 已废弃 | 改它们**毫无效果**。档位模型只从 `user_preferences` 表读,兜底是 `model_whitelist.DEFAULT_TIER_MODELS` |
| `TIER_CLASSIFY_MODEL` **仍在使用** | 别跟着上面那批一起删 |
| `model_whitelist.py` 是严格白名单 | 前端设置页写入的模型必须在白名单内,`anthropic/*` 之类会被拒绝 |
| `scripts/` 下 4 个声音克隆脚本是**预留**状态 | 保留不删、不开发、不接入运行时。详见 `scripts/RESERVED.md` |
| `.gitignore` 里的裸 `data/` 曾静默忽略 `frontend/src/data/demoScript.ts` | v0.10.0 已收紧为 `/data/`。**加 gitignore 规则时必须用前导 `/` 锚定**, 否则匹配任意层级, 且是静默失败 |
| `frontend/src/data/demoScript.ts` 是 v0.10.0 **重建**的, 非原版 | 内容是按类型契约写的合理占位。你若有原版直接覆盖, 只需满足文件头注释里的契约 |
| 前端装依赖**必须加 `--ignore-scripts`** | `electron` 的 postinstall 要下 ~100MB 二进制, 网络不佳时失败。更糟的是 `npm ci` 失败前会**先清空 node_modules**, 导致连 tsc 都跑不了。`启动.bat:110` 用的也是这个参数, CI 与 `scripts/ci.sh` 已照此配置 |
| `npx tsc` 在依赖未装全时会**临时下载别的 TypeScript** | 版本对不上会报 `csstype/index.d.ts ... Unterminated string literal` 之类的假错误。稳妥做法: `node node_modules/typescript/lib/tsc.js --noEmit` |
| TTS 已改浏览器 Web Speech API | `synthesize_speech()` 返回 `None` 是**预期行为**,不是 bug |

---

## 3. 新增知识库:只需丢一个 json

**不要**再去改 `engine.py` 的 `KB_INDEX_FIELD` / `KB_DISPLAY_FIELD` / `_format_result`。
那是 v0.10.0 之前的老做法,漏改任一处都会让新库**静默失效**(不报错,只是永远搜不到)。

```bash
cp my_kb.json backend/knowledge_base/11_my_kb.json
```

需要自定义索引/展示字段时,加一份 manifest:

```jsonc
// backend/knowledge_base/11_my_kb.manifest.json
{
  "index_fields":   ["text", "tags"],
  "display_fields": ["text", "summary"],
  "source":  "https://github.com/xxx/yyy",
  "license": "CC BY 4.0",
  "enabled": true
}
```

- 没 manifest → 走通用兜底,照样能检索
- 引入外部内容**必须**填 `source` 和 `license`(v0.9.8 起 KB 含 CC BY 4.0 / MIT 开源内容,署名是硬要求)
- manifest 文件本身不会被当成知识库加载
- 想确认某个库是否真的被检索到 → `GET /api/settings/knowledge-base`

原有 10 个库(`01_persona` … `10_external_kb`)的 `index_fn` / `display_fn`
原样保留在 `engine.py` 的 `_LEGACY_KB_SCHEMAS` 里,**不要清理**——
它们的行为与通用兜底不等价,改动了会改变既有检索与展示结果。

---

## 4. 新增搜索源:必须遵守签名契约

所有 provider 的签名必须一致:

```python
async def xxx_search(query: str, max_results: int = 10, time_hint: dict = None) -> Dict:
```

`web_search._try_provider_for_all_candidates` 会**无条件**下发 `time_hint=`。
少这个参数就是 `TypeError`,而它被 `except Exception` 吞成一行 warning →
**该源静默死亡且无人察觉**(Tavily 就这样死了一整年)。

注册后记得同步 `tests/test_config_consistency.py` 的 `PROVIDERS` 元组。

---

## 5. 工具执行层的铁律

**任何工具都不能裸 `await`**,必须走超时:

```python
# 对 —— 有超时, 超时后返回结构化降级结果
result = await asyncio.wait_for(execute_tool(name, args), timeout=_tool_timeout(name))

# 错 —— 慢工具会挂死整轮对话(v0.9.7「卡死」类 bug 的根因)
result = await execute_tool(name, args)
```

新增慢工具时,往 `llm_runner.TOOL_TIMEOUTS` 里登记合理上限。

超时后**必须返回降级结果给 LLM**(比如"工具超时,请基于已有信息回答"),
而不是静默丢弃——LLM 拿到降级指令才能继续作答,用户体验才是"没搜到"而非"卡住了"。

---

## 6. 搜索的时间预算

`web_search.py` 顶部有三个预算常量,**调优请改这里**:

- `SEARCH_TIME_BUDGET_SEC = 45.0` — 整轮硬上限
- `PROVIDER_TIMEOUT_SEC = 15.0` — 单源上限
- `SUB_SEARCH_BUDGET_RATIO = 0.4` — 子搜索最多用剩余预算的比例

改动时请保持这个不变式:**墙钟时间与 query 变体数解耦**。
曾经踩过的坑是变体用顺序 for 循环,导致墙钟 = 变体数 × 单次耗时。

---

## 7. 提交前必须跑

```bash
bash scripts/ci.sh            # 一键跑全部 8 项(推荐)
bash scripts/ci.sh --fast     # 跳过前端
```

或分步执行:

```bash
python3 check_imports.py                              # 内部 import 解析
python3 -m compileall -q backend/app                  # 全量语法
python3 -m unittest discover -s tests -p "test_*.py"  # 50 个用例
python3 scripts/check_env.py                          # env 一致性
python3 scripts/search_baseline.py --self-test        # 搜索调度自检(离线)
cd frontend && npx tsc --noEmit && npm run build      # 前端类型 + 构建
```

**测试全部只用标准库,不需要装三方依赖**——这是刻意设计,
目的是让 CI 和任何裸环境都能跑。写新测试请继续遵守。

若修改了被测行为,请**把被测文件回退到 main 版本重跑一次**,
确认测试会失败——否则无法区分"测出真问题"和"恰好通过"。

---

## 8. 写测试的约定

- 放 `tests/`,文件名前缀 `test_`,**只用标准库**(`unittest` + `ast`)
- 需要跨模块 import 时,用 `importlib.util.spec_from_file_location` 按路径加载,
  绕开 `app.*` 包的 `__init__`(它会 import `dotenv` 等三方依赖)
- 注释写**为什么**,不写**是什么**——尤其要写清"这段代码原来坏在哪",
  否则后来的人会以为那是无用代码并"清理"掉

---

## 9. 版本号同步

改版本要同时改三处,漏一处前端会显示旧版本:

1. `backend/app/core/config.py` → `APP_VERSION`
2. `frontend/src/App.tsx` → 页面底部显示串
3. `README.md` 标题

---

## 10. 尚未闭环的事

别以为这些已经好了:

- **CI 没跑起来**:`.github/workflows/ci.yml` 已写好但**未能提交**,
  因为 PAT 与 GitHub App 都缺 `workflows` scope。补齐前靠 `scripts/ci.sh` 本地验证。
- **`main` 已加分支保护**, 但暂不要求 status check(CI 未就位, 强设会导致 PR 全部卡住)。
  workflow 权限补齐后, 应在 GitHub 设置里把 CI 改为必需检查。
- **运行时从未真跑过**:开发环境 PyPI 被墙,`pip install` 不通。
  上面所有结论来自静态分析、AST 检查与桩驱动的单测。
  合并前必须在有依赖的环境做一次真实冒烟。
- **声音克隆合规**:`scripts/RESERVED.md` 里有 A(删除)/B(恢复并规范)两个方向待决策。
