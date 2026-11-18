
import json
import shutil
import subprocess
import uuid

from pathlib import Path


class VideoProcessingError(Exception):
    """Raised when FFmpeg video processing fails."""


def _require_tool(name: str) -> str:
    executable = shutil.which(name)

    if not executable:
        raise VideoProcessingError(
            f"{name} is not installed or is not available in PATH."
        )

    return executable


def get_video_info(video_path: str) -> dict:
    """Read video metadata using FFprobe."""

    source = Path(video_path).resolve()

    if not source.is_file():
        raise VideoProcessingError("Video file was not found.")

    ffprobe = _require_tool("ffprobe")

    command = [
        ffprobe,
        "-v", "error",
        "-show_entries",
        "format=duration,size,format_name:stream=codec_type,codec_name,width,height,r_frame_rate",
        "-of", "json",
        str(source),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )

        metadata = json.loads(result.stdout)
        format_data = metadata.get("format", {})
        streams = metadata.get("streams", [])

        video_stream = next(
            (stream for stream in streams
             if stream.get("codec_type") == "video"),
            None
        )

        if not video_stream:
            raise VideoProcessingError(
                "No video stream was found in this file."
            )

        return {
            "filename": source.name,
            "duration": float(format_data.get("duration", 0)),
            "size_bytes": int(format_data.get("size", 0)),
            "format": format_data.get("format_name", "unknown"),
            "video_codec": video_stream.get("codec_name"),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "frame_rate": video_stream.get("r_frame_rate"),
        }

    except subprocess.TimeoutExpired as exc:
        raise VideoProcessingError("Video inspection timed out.") from exc

    except subprocess.CalledProcessError as exc:
        raise VideoProcessingError(
            exc.stderr or "FFprobe could not read this video."
        ) from exc

    except (ValueError, json.JSONDecodeError) as exc:
        raise VideoProcessingError(
            "Invalid video metadata returned by FFprobe."
        ) from exc


def create_clip(
    video_path: str,
    start_seconds: float,
    end_seconds: float,
    output_dir: str,
) -> dict:
    """
    Extract a real MP4 clip from a source video.

    start_seconds and end_seconds are measured from the beginning
    of the source video.
    """

    source = Path(video_path).resolve()
    destination_dir = Path(output_dir).resolve()

    if not source.is_file():
        raise VideoProcessingError("Source video was not found.")

    if start_seconds < 0:
        raise VideoProcessingError("Start time cannot be negative.")

    if end_seconds <= start_seconds:
        raise VideoProcessingError(
            "End time must be greater than start time."
        )

    info = get_video_info(str(source))
    duration = info["duration"]

    if duration <= 0:
        raise VideoProcessingError("Could not determine video duration.")

    if end_seconds > duration:
        raise VideoProcessingError(
            f"End time exceeds video duration ({duration:.2f} seconds)."
        )

    ffmpeg = _require_tool("ffmpeg")
    destination_dir.mkdir(parents=True, exist_ok=True)

    output_name = f"clip_{uuid.uuid4().hex}.mp4"
    output_path = destination_dir / output_name

    clip_duration = end_seconds - start_seconds

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", str(start_seconds),
        "-i", str(source),
        "-t", str(clip_duration),
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-sn",
        "-dn",
        str(output_path),
    ]

    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=1800,
            check=True,
        )

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise VideoProcessingError(
                "FFmpeg finished but no valid clip was created."
            )

        return {
            "success": True,
            "filename": output_name,
            "path": str(output_path),
            "duration": round(clip_duration, 2),
            "size_bytes": output_path.stat().st_size,
        }

    except subprocess.TimeoutExpired as exc:
        output_path.unlink(missing_ok=True)
        raise VideoProcessingError(
            "Video clipping timed out."
        ) from exc

    except subprocess.CalledProcessError as exc:
        output_path.unlink(missing_ok=True)
        raise VideoProcessingError(
            exc.stderr or "FFmpeg failed to create the clip."
        ) from exc
