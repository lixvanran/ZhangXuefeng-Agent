# 张雪峰语音样本获取指南

要克隆张老师的声音，你需要一个 30 秒 - 2 分钟的清晰音频样本。

## 方法 1：自动下载（推荐，Windows/Mac/Linux 都行）

### 第一步：装依赖
```bash
pip install yt-dlp
```
ffmpeg 也需要安装（用于提取音频）：
- Windows: `choco install ffmpeg`  或  https://ffmpeg.org/download.html
- Mac: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

### 第二步：跑下载脚本
```bash
cd <项目根>
python scripts/download_zhang_audio.py
```

脚本会下载 5 个张雪峰公开演讲（B 站）：
1. 张雪峰封神演讲15分钟完整版 (BV1yb8izPEWW)
2. 张雪峰封神15分钟演讲完整版 (BV1HvYezAEUE)
3. 张雪峰演讲12分钟完整版 (BV1R3hGzHE8u)
4. 张雪峰最震撼的一次封神演讲 (BV1dwu6z1EVn)
5. 演说家: 张雪峰讲为什么考研 (BV1Qx411H71k)

全部保存到 `samples/` 目录，文件名形如 `BV1yb8izPEWW.mp3`。

下载完成后，挑一段**最清晰、语速适中、感情充沛**的（比如 BV1yb8izPEWW），用 ffmpeg 截取 30 秒 - 2 分钟：

```bash
cd samples
# 截取从 30 秒开始，长 1 分钟
ffmpeg -i BV1yb8izPEWW.mp3 -ss 00:00:30 -t 00:01:00 -c copy zhangxuefeng.mp3
```

把截好的 `zhangxuefeng.mp3` 留着（30s-2min 即可）。

## 方法 2：手动下载（如果方法 1 因为 B 站反爬失败）

### 从 B 站：
1. 打开 https://www.bilibili.com
2. 搜索"张雪峰 演讲"
3. 选一个 1-3 分钟的短视频（短视频通常没有水印干扰）
4. 推荐视频（用浏览器无痕模式打开，避免 412）：
   - 封神15分钟: https://www.bilibili.com/video/BV1yb8izPEWW
   - 最震撼的: https://www.bilibili.com/video/BV1dwu6z1EVn
5. 用「唧唧Down」(https://bilibili.iiilab.com/) 或其他在线工具下载 mp3
6. 把 mp3 保存到 `samples/zhangxuefeng.mp3`

### 从抖音：
1. 搜索"张雪峰"，找清晰的访谈/直播片段
2. 用「抖音视频解析」(https://www.douyin.wiki/) 下载
3. 提取音频 (在线工具或 ffmpeg)

### 从微博：
1. 搜索"张雪峰 直播" 或 "张雪峰 演讲"
2. 微博视频可以直接保存到本地

## 方法 3：手机录制（最简单）

1. 用手机打开 B 站或抖音的张雪峰视频
2. 屏幕录制（iOS 控制中心 → 屏幕录制；Android 录屏工具）
3. 录制 1-2 分钟清晰、单一说话人、背景安静的片段
4. 通过微信/QQ 发到电脑
5. 用 ffmpeg 提取音频：
   ```bash
   ffmpeg -i 录制视频.mp4 -vn -ac 1 -ar 16000 zhangxuefeng.mp3
   ```
   - `-vn`: 不要视频
   - `-ac 1`: 单声道
   - `-ar 16000`: 16kHz 采样率 (够用)

## 音频质量要求

✅ 推荐：
- **单声道** (mono)
- **采样率 16kHz 或 22kHz** (太高浪费，太低失真)
- **时长 30 秒 - 2 分钟** (太短克隆效果差, 太长没必要)
- **背景安静** (无背景音乐 / 多人对话)
- **mp3 / m4a / wav** 格式

❌ 避免：
- 多个人对话 (克隆会混入其他声线)
- 背景音乐很响 (克隆会学到音乐)
- 时长 < 15 秒 (效果差)
- 时长 > 5 分钟 (浪费, 上传慢)

## 下一步：克隆

下载好 `samples/zhangxuefeng.mp3` 后：

```bash
# Windows
cd <项目根>
set PYTHONUTF8=1
python scripts\clone_zhang_voice.py

# Mac/Linux
python scripts/clone_zhang_voice.py
```

脚本会：
1. 上传你的样本
2. 调用 MiniMax `clone_voice` API
3. 写入 `backend/.env` 的 `ZHANG_VOICE_ID=...`
4. 后端重启后 TTS 就会用张老师的声音

## 如果不克隆

直接用默认 `male-qn-qingse` 男声（稳重男声，已经比较接近张雪峰）。
在浏览器上点 AI 回答的 🔊 朗读按钮，立刻能听到。

## 张雪峰公开演讲清单（参考）

| 平台 | 视频 | 时长 | 备注 |
|---|---|---|---|
| B 站 | BV1yb8izPEWW | 15 min | 封神演讲完整版 |
| B 站 | BV1HvYezAEUE | 15 min | 另一版封神 |
| B 站 | BV1R3hGzHE8u | 12 min | 12分钟版 |
| B 站 | BV1dwu6z1EVn | 17 min | 最震撼的一次 |
| B 站 | BV1Qx411H71k | 15 min | 演说家讲考研 |
| 微博 | @张雪峰老师 主页 | 大量 | 日常直播片段 |
| 抖音 | "张雪峰" 搜索 | 大量 | 短视频, 1-3 分钟 |
