#!/usr/bin/env python3
"""Generate a demo voice sample using MiniMax TTS.

If you don't have a Zhang Xuefeng audio sample, this script uses MiniMax's
default TTS voice to generate a 60-second 'demo' audio file. This is NOT
Zhang's real voice (you need a real sample for that), but it lets you
test the clone_voice.py flow end-to-end.

After running this script, you'll have samples/demo_voice.mp3 that you
can copy to samples/zhangxuefeng.mp3 and then run clone_zhang_voice.py.

Real usage: replace samples/demo_voice.mp3 with an actual Zhang Xuefeng
sample (see samples/INSTRUCTIONS.md for how to get one).
"""
import os
import sys
import subprocess
from pathlib import Path

# Add backend to path
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "backend"
SAMPLES = HERE.parent / "samples"
sys.path.insert(0, str(BACKEND))

# Zhang Xuefeng's signature phrases (use these for the demo)
DEMO_PHRASES = [
    "兄弟，你问报志愿的事儿，我跟你讲啊，听我说。",
    "选择比努力更重要，但有得选的前提是你足够努力。",
    "家里没矿别谈理想，学习是老实人家孩子唯一的出路。",
    "你以为你选的是专业，其实你选的是四年后站在哪个赛道上。",
    "城市有时候比学校更重要。在哪里读书，大概率就在哪里工作。",
    "考研不是逃避就业的避风港。如果你考研只是因为不想找工作，那三年后你还是不想。",
    "信息差是最贵的差距。有人花四年才发现自己走错了路，你花四分钟就能避开。",
    "这个世界上最难过的事，不是失败，是你明明可以做出更好的选择，但因为不知道而错过了。",
    "普通人别总想着逆袭，先学会不掉队。不掉队本身就是胜利。",
    "理工科专业大于学校，文科学校大于专业。记住这句话，能少走很多弯路。",
]


def main():
    from app.core.config import settings
    if not settings.LLM_API_KEY:
        print("ERROR: LLM_API_KEY not set in backend/.env")
        sys.exit(1)
    import httpx
    import base64
    SAMPLES.mkdir(parents=True, exist_ok=True)
    out_mp3 = SAMPLES / "demo_voice.mp3"
    full_text = " ".join(DEMO_PHRASES)
    print(f"Generating demo voice ({len(full_text)} chars)...")
    print(f"Text preview: {DEMO_PHRASES[0]}...")
    print()
    audio_segments = []
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}
    for i, phrase in enumerate(DEMO_PHRASES, 1):
        print(f"  [{i}/{len(DEMO_PHRASES)}] {phrase[:30]}...")
        try:
            resp = httpx.post(
                "https://api.minimax.chat/v1/t2a_v2",
                headers=headers,
                json={
                    "model": "speech-01-turbo",
                    "text": phrase,
                    "voice_setting": {
                        "voice_id": "male-qn-qingse",
                        "speed": 1.0,
                        "vol": 1.0,
                        "pitch": 0,
                    },
                    "audio_setting": {
                        "sample_rate": 32000,
                        "format": "mp3",
                    },
                },
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                audio_b64 = data.get("data", {}).get("audio") or data.get("audio", "")
                if audio_b64:
                    audio_segments.append(base64.b64decode(audio_b64))
        except Exception as e:
            print(f"      FAIL: {e}")
    if not audio_segments:
        print("ERROR: No audio generated. Check API key / network.")
        sys.exit(1)
    # Concatenate mp3 segments using ffmpeg
    with open("/tmp/_seg.mp3", "wb") as f:
        for seg in audio_segments:
            f.write(seg)
    # Re-encode to a clean 16kHz mono mp3
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", "/tmp/_seg.mp3", "-ar", "16000", "-ac", "1",
             "-codec:a", "libmp3lame", "-q:a", "5", str(out_mp3)],
            check=True, capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"ffmpeg error: {e}")
        # Fallback: just save the raw concatenated mp3
        out_mp3.write_bytes(audio_segments[0] if len(audio_segments) == 1 else b"".join(audio_segments))
    size_mb = out_mp3.stat().st_size / 1024 / 1024
    print()
    print("=" * 60)
    print(f"Demo voice saved: {out_mp3} ({size_mb:.1f} MB)")
    print()
    print("This is NOT Zhang's voice — it's a generic male voice used to")
    print("test the clone_voice flow. To get Zhang's REAL voice, see")
    print("samples/INSTRUCTIONS.md for how to download a real sample.")
    print()
    print("To use this demo for testing the clone flow:")
    print(f"  cp {out_mp3} {SAMPLES / 'zhangxuefeng.mp3'}")
    print("  python scripts/clone_zhang_voice.py")


if __name__ == "__main__":
    main()
