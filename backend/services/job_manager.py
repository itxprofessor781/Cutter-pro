
import logging
import threading
import uuid

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from config import settings

from services.video_processor import (
    get_video_info,
    create_clip,
)

from services.transcription import (
    transcribe_video,
)

from services.clip_selector import (
    select_viral_clips,
)


logger = logging.getLogger("cutter_ai.jobs")

# Start with one worker to avoid overloading a small server.
_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="cutter-ai-worker",
)

_jobs = {}
_jobs_lock = threading.RLock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _update_job(job_id, **changes):
    with _jobs_lock:
        job = _jobs.get(job_id)

        if job is None:
            return

        job.update(changes)
        job["updated_at"] = _now()


def register_upload(
    job_id: str,
    file_path: str,
    filename: str,
):
    """Register an uploaded video with the job manager."""

    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "filename": filename,
            "file_path": str(Path(file_path).resolve()),
            "status": "uploaded",
            "progress": 0,
            "stage": "Video uploaded",
            "video_info": None,
            "transcript": None,
            "clips": [],
            "error": None,
            "created_at": _now(),
            "updated_at": _now(),
        }

    return get_job(job_id)


def get_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)

        if job is None:
            return None

        return dict(job)


def list_jobs():
    with _jobs_lock:
        return [
            dict(job)
            for job in _jobs.values()
        ]


def _run_pipeline(
    job_id: str,
    number_of_clips: int,
    min_duration: int,
    max_duration: int,
    language=None,
):
    """Run the complete video-to-clips pipeline."""

    job = get_job(job_id)

    if job is None:
        return

    try:
        source = job["file_path"]

        _update_job(
            job_id,
            status="processing",
            progress=5,
            stage="Inspecting video",
        )

        video_info = get_video_info(source)

        _update_job(
            job_id,
            progress=15,
            stage="Transcribing speech",
            video_info=video_info,
        )

        transcript = transcribe_video(
            source,
            model_name=settings.WHISPER_MODEL,
            device=settings.WHISPER_DEVICE,
            compute_type=settings.WHISPER_COMPUTE_TYPE,
            language=language,
        )

        _update_job(
            job_id,
            progress=50,
            stage="Finding engaging moments",
            transcript=transcript,
        )

        selection = select_viral_clips(
            transcript=transcript,
            number_of_clips=number_of_clips,
            min_duration=min_duration,
            max_duration=max_duration,
        )

        selected_clips = selection["clips"]

        if not selected_clips:
            raise RuntimeError(
                "AI could not find any valid clips. "
                "Try different duration settings."
            )

        _update_job(
            job_id,
            progress=65,
            stage="Creating MP4 clips",
        )

        output_dir = (
            settings.OUTPUT_DIR / job_id
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        completed_clips = []

        for index, clip in enumerate(selected_clips):
            result = create_clip(
                video_path=source,
                start_seconds=clip["start"],
                end_seconds=clip["end"],
                output_dir=str(output_dir),
            )

            completed_clips.append({
                **clip,
                "clip_id": str(uuid.uuid4()),
                "filename": result["filename"],
                "path": result["path"],
                "size_bytes": result["size_bytes"],
                "status": "completed",
            })

            progress = 65 + int(
                30 * (index + 1) / len(selected_clips)
            )

            _update_job(
                job_id,
                progress=progress,
                clips=completed_clips,
                stage=f"Creating clip {index + 1} of {len(selected_clips)}",
            )

        _update_job(
            job_id,
            status="completed",
            progress=100,
            stage="All clips are ready",
            clips=completed_clips,
            error=None,
        )

    except Exception as exc:
        logger.exception(
            "Video processing failed for job %s",
            job_id,
        )

        _update_job(
            job_id,
            status="failed",
            progress=0,
            stage="Processing failed",
            error=str(exc)[:1000],
        )


def start_processing(
    job_id: str,
    number_of_clips: int = 5,
    min_duration: int = 15,
    max_duration: int = 60,
    language=None,
):
    """Queue an uploaded video for processing."""

    if not 1 <= number_of_clips <= 20:
        raise ValueError(
            "Number of clips must be between 1 and 20."
        )

    if min_duration < 5 or max_duration < min_duration:
        raise ValueError("Invalid clip duration settings.")

    with _jobs_lock:
        job = _jobs.get(job_id)

        if job is None:
            raise ValueError("Job not found.")

        if job["status"] not in ("uploaded", "failed"):
            raise ValueError(
                "This job is already processing or completed."
            )

        job["status"] = "queued"
        job["progress"] = 1
        job["stage"] = "Waiting for processing worker"
        job["error"] = None
        job["updated_at"] = _now()

    _executor.submit(
        _run_pipeline,
        job_id,
        number_of_clips,
        min_duration,
        max_duration,
        language,
    )

    return get_job(job_id)
