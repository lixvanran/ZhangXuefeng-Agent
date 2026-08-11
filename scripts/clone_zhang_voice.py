#!/usr/bin/env python3
"""Clone Zhang Xuefeng's voice from a local audio sample.

Usage:
    1. Place a 30s-2min audio sample at samples/zhangxuefeng.mp3
       (or .wav / .m4a)
    2. Run: python scripts/clone_zhang_voice.py
    3. The script uploads the sample, runs clone_voice, and writes the
       resulting voice_id to backend/.env (ZHANG_VOICE_ID=...)
    4. Restart the backend; TTS will use the cloned voice

If you don't have a sample, the backend will use the default
male-qn-qingse voice, which is already a steady male voice close to
Zhang's style. So this script is OPTIONAL.
"""
import os
import sys
import re
from pathlib import Path

# Add backend to path
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "backend"
sys.path.insert(0, str(BACKEND))

SAMPLES_DIR = HERE.parent / "samples"
ENV_FILE = BACKEND / ".env"


def find_sample() -> Path:
    """Look for a sample audio file in samples/"""
    if not SAMPLES_DIR.exists():
        print(f"ERROR: {SAMPLES_DIR} does not exist. Create it first.")
        sys.exit(1)
    for ext in [".mp3", ".wav", ".m4a", ".flac", ".ogg"]:
        for f in SAMPLES_DIR.glob(f"*{ext}"):
            return f
    print(f"ERROR: No audio sample found in {SAMPLES_DIR}")
    print("Please place a 30s-2min audio file (mp3/wav/m4a) there, e.g.:")
    print(f"  {SAMPLES_DIR}/zhangxuefeng.mp3")
    sys.exit(1)


def main():
    sample = find_sample()
    print(f"Found sample: {sample}")
    size_mb = sample.stat().st_size / 1024 / 1024
    print(f"Size: {size_mb:.2f} MB")
    if size_mb > 20:
        print(f"WARNING: Sample is {size_mb:.1f}MB. The API may reject files > 20MB.")
        print("Consider trimming to 30s-2min for best results.")
    print()
    # 1. Upload
    print("Step 1/3: Uploading sample...")
    from app.core.config import settings
    if not settings.LLM_API_KEY:
        print("ERROR: LLM_API_KEY not set in backend/.env")
        sys.exit(1)
    # Use the MiniMax-hosted clone API
    import httpx
    upload_url = "https://api.minimax.chat/v1/files/upload"
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}
    try:
        with open(sample, "rb") as f:
            r = httpx.post(
                upload_url,
                headers=headers,
                files={"file": (sample.name, f, "audio/mpeg")},
                data={"purpose": "voice_clone"},
                timeout=60,
            )
        if r.status_code != 200:
            print(f"Upload failed: HTTP {r.status_code} {r.text[:300]}")
            sys.exit(1)
        file_id = r.json().get("file", {}).get("id") or r.json().get("id")
        if not file_id:
            print(f"Upload response missing file_id: {r.text[:300]}")
            sys.exit(1)
        print(f"  Uploaded: {file_id}")
    except Exception as e:
        print(f"Upload error: {e}")
        sys.exit(1)
    # 2. Clone
    print("Step 2/3: Cloning voice...")
    clone_url = "https://api.minimax.chat/v1/voice_clone"
    try:
        r = httpx.post(
            clone_url,
            headers={**headers, "Content-Type": "application/json"},
            json={
                "file_id": file_id,
                "voice_id": f"zhangxuefeng_{os.getpid()}",
                "model": "speech-01",
                "text": "同学们好，我是张老师，今天咱们来聊聊高考报志愿的事儿。",
            },
            timeout=120,
        )
        if r.status_code not in (200, 201):
            print(f"Clone failed: HTTP {r.status_code} {r.text[:300]}")
            sys.exit(1)
        result = r.json()
        voice_id = (
            result.get("voice_id")
            or result.get("data", {}).get("voice_id")
            or result.get("id")
        )
        if not voice_id:
            print(f"Clone response missing voice_id: {r.text[:300]}")
            sys.exit(1)
        print(f"  Cloned voice_id: {voice_id}")
    except Exception as e:
        print(f"Clone error: {e}")
        sys.exit(1)
    # 3. Write to .env
    print("Step 3/3: Writing voice_id to backend/.env...")
    if not ENV_FILE.exists():
        print(f"ERROR: {ENV_FILE} does not exist. Run 启动.bat first.")
        sys.exit(1)
    text = ENV_FILE.read_text(encoding="utf-8")
    if re.search(r"^ZHANG_VOICE_ID=.*", text, re.MULTILINE):
        text = re.sub(r"^ZHANG_VOICE_ID=.*", f"ZHANG_VOICE_ID={voice_id}", text, flags=re.MULTILINE)
    else:
        # Add before TAVILY_API_KEY block (or at the end)
        if "TAVILY_API_KEY" in text:
            text = text.replace(
                "TAVILY_API_KEY=",
                f"# ===== v0.7.9.4: Zhang's cloned voice (set by clone_zhang_voice.py) =====\nZHANG_VOICE_ID={voice_id}\n\nTAVILY_API_KEY=",
                1,
            )
        else:
            text += f"\nZHANG_VOICE_ID={voice_id}\n"
    ENV_FILE.write_text(text, encoding="utf-8")
    print(f"  Written to {ENV_FILE}")
    print()
    print("=" * 50)
    print(f"  Done! Voice id: {voice_id}")
    print(f"  Restart the backend (启动.bat) to use the cloned voice.")
    print(f"  Test: visit  http://localhost:3000  and click 朗读 on any message")
    print("=" * 50)


if __name__ == "__main__":
    main()
