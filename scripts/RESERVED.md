# scripts/ — 状态说明

> 本目录下的脚本分两类:**在用** 与 **预留**。请勿在不确认状态的情况下改动或删除。

---

## 预留(暂存,不参与运行时)

以下 4 个脚本与「张雪峰声音克隆」相关,**2026-10-02 起标记为预留状态**:

| 脚本 | 作用 | 当前状态 |
|---|---|---|
| `clone_zhang_voice.py` | 上传音频样本 → 调 MiniMax `clone_voice` → 写入 `ZHANG_VOICE_ID` | **未接入应用** |
| `download_zhang_audio.py` | 从 B 站抓取公开演讲视频并提取音频 | **未接入应用** |
| `generate_demo_voice.py` | 用 MiniMax 默认音色生成 60s 演示音频 | **未接入应用** |
| `../samples/INSTRUCTIONS.md` | 声音样本获取指南 | 仅文档 |

### 为什么是「预留」而不是「已废弃」

这套脚本针对的是**真实公众人物**的声音,涉及授权与合规问题。
在明确决策之前,采取「保留但明确标记」的处理:

- **不删除** —— 保留可能的后续选择权
- **不开发** —— 暂不投入维护
- **不接入运行时** —— 保持休眠,不影响产品

### 技术状态:确认为休眠

v0.9.8 起,TTS 已改为**浏览器 Web Speech API**,后端不再合成音频:

```python
# backend/app/services/tts_service.py
async def synthesize_speech(text, voice_id=None, speed=1.0) -> Optional[bytes]:
    """v0.10.0 stub: TTS 改用浏览器 Web Speech API, 后端不再合成音频
    返回 None — 前端已用 window.speechSynthesis.speak() 直接读
    """
    return None
```

`ZHANG_VOICE_ID` 仅在 `backend/app/core/config.py:118` 声明,**无任何读取方**。
即:即使执行了 `clone_zhang_voice.py` 写入 voice_id,后端也不会使用它。

`tests/test_reserved_scripts.py` 会持续校验这一休眠状态(见下)。

### 后续决策的两个方向

**方向 A — 删除**
移除本目录 3 个脚本与 `samples/INSTRUCTIONS.md`,同时清理
`config.py` 的 `ZHANG_VOICE_ID` 字段。合规风险归零。

**方向 B — 恢复并规范**
需要先满足:

1. 确认声音使用权(本人授权 / 公开许可素材 / 其他合法来源)
2. 恢复 `synthesize_speech()` 的实际合成能力(需重新引入 TTS 依赖)
3. 接入 `model_whitelist` 或独立配置项, 让 voice_id 可被选择
4. 补上 CI 对该路径的覆盖

⚠️ **在未做出上述决策前,不要执行这些脚本,也不要让它们进入主链路。**

---

## 在用

| 脚本 | 作用 |
|---|---|
| `test_key.py` | OpenRouter Key 连通性验证,不依赖项目代码,可独立运行。与声音克隆无关。 |

---

## 维护约定

`tests/test_reserved_scripts.py` 锁定以下事实,改动本目录时需同步:

- 4 个预留脚本仍然存在(被误删即测试失败)
- `synthesize_speech()` 仍返回 `None`(被接入即测试失败)
- `ZHANG_VOICE_ID` 仍无读取方(被接入即测试失败)
- 本说明文件存在(避免状态失联)
