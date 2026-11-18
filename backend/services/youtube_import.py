
import re
from pathlib import Path

import yt_dlp

from config import settings


YOUTUBE_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def validate_youtube_url(url: str):
    from urllib.parse import urlparse

    parsed = urlparse(url.strip())

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only HTTP and HTTPS YouTube URLs are allowed.")

    if (parsed.hostname or "").lower() not in YOUTUBE_DOMAINS:
        raise ValueError("Please provide a valid YouTube URL.")

    if parsed.username or parsed.password:
        raise ValueError("Invalid YouTube URL.")

    return url.strip()


def download_youtube_video(url: str, job_id: str):
    url = validate_youtube_url(url)

    output_dir = Path(settings.UPLOAD_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(output_dir / f"{job_id}.%(ext)s")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "max_filesize": max_bytes,
        "restrictfilenames": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(
                url,
                download=True,
            )

        files = [
            path for path in output_dir.glob(f"{job_id}.*")
            if path.is_file()
            and path.suffix.lower() in {
                ".mp4", ".webm", ".mkv", ".mov"
            }
            and not path.name.endswith(".part")
        ]

        if not files:
            raise RuntimeError("Downloaded video file was not found.")

        video_path = max(files, key=lambda path: path.stat().st_size)

        if video_path.stat().st_size > max_bytes:
            video_path.unlink(missing_ok=True)
            raise RuntimeError("Video exceeds the configured upload size limit.")

        if video_path.stat().st_size == 0:
            video_path.unlink(missing_ok=True)
            raise RuntimeError("Downloaded video is empty.")

        return {
            "path": str(video_path.resolve()),
            "filename": re.sub(
                r'[\\/:*?"<>|]',
                "_",
                info.get("title") or "youtube-video",
            )[:150],
            "title": info.get("title") or "YouTube video",
            "duration": info.get("duration"),
        }

    except Exception:
        for path in output_dir.glob(f"{job_id}.*"):
            if path.is_file():
                path.unlink(missing_ok=True)
        raise
