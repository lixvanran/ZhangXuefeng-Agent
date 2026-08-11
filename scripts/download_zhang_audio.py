#!/usr/bin/env python3
"""Download Zhang Xuefeng's public speech videos and extract audio.

This script helps you collect audio samples for voice cloning (see
scripts/clone_zhang_voice.py). It downloads a curated list of Zhang's
public speeches from Bilibili, extracts the audio, and saves them to
samples/ in mp3 format.

REQUIREMENTS:
    pip install yt-dlp
    # ffmpeg must be installed (for audio extraction)
    # Windows: choco install ffmpeg   OR   https://ffmpeg.org/download.html
    # Mac:     brew install ffmpeg
    # Linux:   sudo apt install ffmpeg

USAGE:
    python scripts/download_zhang_audio.py
    python scripts/download_zhang_audio.py --max 3     # download only 3 videos
    python scripts/download_zhang_audio.py --out samples/  # output to samples/
"""
import os
import sys
import argparse
import subprocess
from pathlib import Path

# Curated list of Zhang Xuefeng's public speeches
# (B 站 BV 号, 标题, 时长, 备注)
SPEECHES = [
    ("BV1yb8izPEWW", "张雪峰封神演讲15分钟完整版 (2025-07-28)", "~15 min", "必听, 语速适中, 口音清晰"),
    ("BV1HvYezAEUE", "张雪峰封神15分钟演讲完整版 (2025-08-18)", "~15 min", "语速快, 信息密度大"),
    ("BV1R3hGzHE8u", "张雪峰演讲12分钟完整版 (2025-08-04)", "~12 min", "对话式, 节奏自然"),
    ("BV1dwu6z1EVn", "张雪峰最震撼的一次封神演讲", "~17 min", "激情澎湃, 适合克隆声线"),
    ("BV1Qx411H71k", "演说家: 张雪峰讲为什么考研 (2017-08-04)", "~15 min", "早期作品, 语速较慢"),
]


def check_ytdlp():
    try:
        import yt_dlp
    except ImportError:
        print("ERROR: yt-dlp not installed.")
        print("Run: pip install yt-dlp")
        sys.exit(1)
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ERROR: ffmpeg not found.")
        print("Install ffmpeg:")
        print("  Windows: https://ffmpeg.org/download.html or choco install ffmpeg")
        print("  Mac:     brew install ffmpeg")
        print("  Linux:   sudo apt install ffmpeg")
        sys.exit(1)


def download_one(bv_id: str, title: str, out_dir: Path) -> Path:
    """Download one B 站 video and extract audio as mp3."""
    import yt_dlp
    url = f"https://www.bilibili.com/video/{bv_id}"
    print(f"\n=== Downloading: {title} ===")
    print(f"    URL: {url}")
    out_template = str(out_dir / f"{bv_id}.%(ext)s")
    ydl_opts = {
        "outtmpl": out_template,
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "noplaylist": True,
        "quiet": False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        mp3_path = out_dir / f"{bv_id}.mp3"
        if mp3_path.exists():
            size_mb = mp3_path.stat().st_size / 1024 / 1024
            print(f"    [OK] {mp3_path.name} ({size_mb:.1f} MB)")
            return mp3_path
        else:
            print(f"    [WARN] Download completed but mp3 not found")
            return None
    except Exception as e:
        print(f"    [FAIL] {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Download Zhang Xuefeng's speeches for voice cloning")
    parser.add_argument("--out", default="samples", help="Output directory (default: samples/)")
    parser.add_argument("--max", type=int, default=len(SPEECHES), help="Max number of videos to download")
    parser.add_argument("--list", action="store_true", help="Just list the videos, don't download")
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {out_dir.absolute()}")
    print()
    if args.list:
        print("Available speeches:")
        for i, (bv, title, dur, note) in enumerate(SPEECHES, 1):
            print(f"  [{i}] {bv} | {dur} | {title}")
            print(f"      {note}")
        return
    check_ytdlp()
    print(f"Will download up to {args.max} videos\n")
    downloaded = []
    for bv, title, dur, note in SPEECHES[: args.max]:
        result = download_one(bv, title, out_dir)
        if result:
            downloaded.append(result)
    print()
    print("=" * 60)
    print(f"Downloaded {len(downloaded)} / {min(args.max, len(SPEECHES))} videos")
    for p in downloaded:
        print(f"  - {p}")
    if downloaded:
        # 提示合并
        print()
        print("Next step: pick the best 30s-2min segment from one of these,")
        print("or concatenate them with ffmpeg:")
        print(f"  cd {out_dir}")
        print("  # Pick 30s-2min segment from the most clearly-spoken one")
        print("  ffmpeg -i BV1yb8izPEWW.mp3 -ss 00:00:30 -t 00:01:30 zhangxuefeng.mp3")
        print()
        print("Then run: python scripts/clone_zhang_voice.py")
    else:
        print()
        print("No videos downloaded. You can also download from:")
        print("  - B 站 (https://www.bilibili.com) — search '张雪峰 演讲'")
        print("  - 微博 (https://weibo.com) — search '张雪峰'")
        print("  - 抖音 (https://www.douyin.com) — search '张雪峰'")


if __name__ == "__main__":
    main()
