
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered video clipping platform"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Temporary job registry.
# Persistent job storage will be added in a later step.
jobs = {}

ALLOWED_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"
}


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "message": "CUTTER AI Backend is running",
        "version": settings.APP_VERSION
    }


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "backend": "online",
        "app": settings.APP_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No filename provided"
        )

    original_name = Path(file.filename).name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported video format"
        )

    job_id = str(uuid.uuid4())
    safe_filename = f"{job_id}{extension}"
    file_path = settings.UPLOAD_DIR / safe_filename

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_bytes = 0

    try:
        with file_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_bytes += len(chunk)

                if total_bytes > max_bytes:
                    destination.close()
                    file_path.unlink(missing_ok=True)

                    raise HTTPException(
                        status_code=413,
                        detail="Video exceeds the maximum upload size"
                    )

                destination.write(chunk)

    except HTTPException:
        raise
    except Exception:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="Video upload failed"
        )
    finally:
        await file.close()

    jobs[job_id] = {
        "job_id": job_id,
        "filename": original_name,
        "stored_filename": safe_filename,
        "file_path": str(file_path),
        "status": "uploaded",
        "progress": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    return {
        "success": True,
        "message": "Video uploaded successfully",
        "job": {
            "job_id": job_id,
            "filename": original_name,
            "status": "uploaded",
            "progress": 0
        }
    }


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = jobs.get(job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    return {
        "success": True,
        "job": {
            "job_id": job["job_id"],
            "filename": job["filename"],
            "status": job["status"],
            "progress": job["progress"],
            "created_at": job["created_at"]
        }
    }


@app.get("/api/jobs")
async def list_jobs():
    return {
        "success": True,
        "total": len(jobs),
        "jobs": [
            {
                "job_id": job["job_id"],
                "filename": job["filename"],
                "status": job["status"],
                "progress": job["progress"]
            }
            for job in jobs.values()
        ]
    }
