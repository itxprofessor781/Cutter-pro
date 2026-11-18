
import uuid
import asyncio
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import settings
from services.job_manager import (
    register_upload,
    start_processing,
    get_job,
    list_jobs,
)
from services.youtube_import import download_youtube_video


router = APIRouter(prefix="/api", tags=["CUTTER AI"])


ALLOWED_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"
}


class ProcessRequest(BaseModel):
    number_of_clips: int = Field(default=5, ge=1, le=20)
    min_duration: int = Field(default=15, ge=5, le=600)
    max_duration: int = Field(default=60, ge=5, le=600)
    language: str | None = None


class YouTubeImportRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=2048)
    rights_confirmed: bool = False


def public_job(job: dict) -> dict:
    """Remove internal server paths from API responses."""

    return {
        "job_id": job["job_id"],
        "filename": job["filename"],
        "status": job["status"],
        "progress": job["progress"],
        "stage": job["stage"],
        "video_info": job.get("video_info"),
        "clips": [
            {
                key: clip.get(key)
                for key in (
                    "clip_id",
                    "filename",
                    "title",
                    "reason",
                    "hook",
                    "score",
                    "start",
                    "end",
                    "duration",
                    "size_bytes",
                    "status",
                )
            }
            for clip in job.get("clips", [])
        ],
        "error": job.get("error"),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }


@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "Filename is required.")

    original_name = Path(file.filename).name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            "Unsupported video format."
        )

    job_id = str(uuid.uuid4())
    safe_filename = f"{job_id}{extension}"
    destination = settings.UPLOAD_DIR / safe_filename

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_bytes = 0

    try:
        with destination.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_bytes += len(chunk)

                if total_bytes > max_bytes:
                    raise HTTPException(
                        413,
                        "Video exceeds the upload size limit."
                    )

                output.write(chunk)

        if total_bytes == 0:
            raise HTTPException(400, "Uploaded file is empty.")

        job = register_upload(
            job_id=job_id,
            file_path=str(destination),
            filename=original_name,
        )

        return {
            "success": True,
            "message": "Video uploaded successfully.",
            "job": public_job(job),
        }

    except HTTPException:
        destination.unlink(missing_ok=True)
        raise

    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            500,
            f"Upload failed: {str(exc)}"
        ) from exc

    finally:
        await file.close()


@router.post("/youtube/import")
async def import_youtube_video(request: YouTubeImportRequest):
    if not request.rights_confirmed:
        raise HTTPException(
            400,
            "Please confirm that you own this video or have permission to process it."
        )

    job_id = str(uuid.uuid4())
    downloaded_file = None

    try:
        downloaded_file = await asyncio.to_thread(
            download_youtube_video,
            request.url,
            job_id
        )

        file_path = downloaded_file["path"]
        filename = Path(file_path).name

        job = register_upload(
            job_id=job_id,
            file_path=file_path,
            filename=filename,
        )

        return {
            "success": True,
            "message": "YouTube video imported successfully.",
            "job": public_job(job),
        }

    except ValueError as exc:
        if downloaded_file:
            Path(downloaded_file["path"]).unlink(missing_ok=True)

        raise HTTPException(
            400,
            str(exc)
        ) from exc

    except Exception as exc:
        if downloaded_file:
            Path(downloaded_file["path"]).unlink(missing_ok=True)

        raise HTTPException(
            502,
            "YouTube video could not be imported. It may be unavailable or restricted."
        ) from exc


@router.post("/process/{job_id}")
async def process_video(
    job_id: str,
    request: ProcessRequest,
):
    try:
        job = start_processing(
            job_id=job_id,
            number_of_clips=request.number_of_clips,
            min_duration=request.min_duration,
            max_duration=request.max_duration,
            language=request.language,
        )

        return {
            "success": True,
            "message": "Video processing has been queued.",
            "job": public_job(job),
        }

    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/jobs")
async def all_jobs():
    jobs = list_jobs()

    return {
        "success": True,
        "total": len(jobs),
        "jobs": [public_job(job) for job in jobs],
    }


@router.get("/jobs/{job_id}")
async def job_status(job_id: str):
    job = get_job(job_id)

    if not job:
        raise HTTPException(404, "Job not found.")

    return {
        "success": True,
        "job": public_job(job),
    }


@router.get("/download/{job_id}/{clip_id}")
async def download_clip(job_id: str, clip_id: str):
    job = get_job(job_id)

    if not job:
        raise HTTPException(404, "Job not found.")

    clip = next(
        (
            item for item in job.get("clips", [])
            if item.get("clip_id") == clip_id
        ),
        None,
    )

    if not clip:
        raise HTTPException(404, "Clip not found.")

    output_root = settings.OUTPUT_DIR.resolve()
    clip_path = Path(clip["path"]).resolve()

    if not clip_path.is_relative_to(output_root):
        raise HTTPException(403, "Invalid file path.")

    if not clip_path.is_file():
        raise HTTPException(404, "Clip file is unavailable.")

    return FileResponse(
        path=clip_path,
        media_type="video/mp4",
        filename=clip.get("filename", "cutter-clip.mp4"),
    )
