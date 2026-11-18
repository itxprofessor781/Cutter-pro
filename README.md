
# CUTTER AI

AI-powered video clipping platform that analyzes videos, identifies interesting moments, and creates short MP4 clips.

## Features

- Video upload
- AI-powered transcription using Faster-Whisper
- AI clip selection using Ollama
- Automatic MP4 clip generation using FFmpeg
- Job progress tracking
- Individual clip downloads

## Technology Stack

- Python 3.11
- FastAPI
- Faster-Whisper
- Ollama (Llama 3.2)
- FFmpeg
- Docker and Docker Compose

## Project Structure

```text
CUTTER-AI/
├── backend/
│   ├── api/
│   ├── services/
│   ├── storage/
│   ├── config.py
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
├── .gitignore
└── README.md
```

## Run With Docker

Make sure Docker and Docker Compose are installed.

Start the services:

```bash
docker compose up --build -d
```

Download the AI model:

```bash
docker exec cutter-ai-ollama ollama pull llama3.2
```

## API

Once the backend is running:

- API: http://localhost:8000
- Health Check: http://localhost:8000/api/health
- API Documentation: http://localhost:8000/docs

## Environment Variables

See `backend/.env.example` for configuration examples.

## Storage

Uploaded videos and generated clips are stored in persistent Docker volumes.

## Important

This project requires a server with sufficient CPU, RAM, and disk space for video processing and AI inference.

YouTube downloading and processing must comply with applicable copyright laws and platform terms.

## Project Status

Backend development and deployment configuration are in progress.
