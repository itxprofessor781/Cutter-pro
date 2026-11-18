
from pathlib import Path
from faster_whisper import WhisperModel


class TranscriptionError(Exception):
    """Raised when speech transcription fails."""


_model = None
_loaded_model_name = None


def get_model(model_name="base", device="cpu", compute_type="int8"):
    """
    Load Faster-Whisper model once and reuse it.
    Available model sizes include tiny, base, small, medium and large-v3.
    """

    global _model, _loaded_model_name

    model_key = f"{model_name}:{device}:{compute_type}"

    if _model is not None and _loaded_model_name == model_key:
        return _model

    try:
        _model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )

        _loaded_model_name = model_key
        return _model

    except Exception as exc:
        _model = None
        _loaded_model_name = None

        raise TranscriptionError(
            f"Could not load Whisper model: {exc}"
        ) from exc


def transcribe_video(
    video_path: str,
    model_name="base",
    device="cpu",
    compute_type="int8",
    language=None,
):
    """
    Transcribe speech from an audio or video file.
    Returns transcript segments with timestamps.
    """

    source = Path(video_path).resolve()

    if not source.is_file():
        raise TranscriptionError("Video file was not found.")

    try:
        model = get_model(
            model_name=model_name,
            device=device,
            compute_type=compute_type,
        )

        segments, info = model.transcribe(
            str(source),
            language=language,
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
        )

        results = []
        full_text = []

        for segment in segments:
            text = segment.text.strip()

            if not text:
                continue

            words = []

            if segment.words:
                for word in segment.words:
                    words.append({
                        "word": word.word,
                        "start": round(word.start, 3),
                        "end": round(word.end, 3),
                        "probability": word.probability,
                    })

            results.append({
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "text": text,
                "words": words,
            })

            full_text.append(text)

        return {
            "success": True,
            "language": info.language,
            "language_probability": round(
                info.language_probability, 4
            ),
            "duration": round(info.duration, 2),
            "text": " ".join(full_text),
            "segments": results,
        }

    except TranscriptionError:
        raise

    except Exception as exc:
        raise TranscriptionError(
            f"Transcription failed: {exc}"
        ) from exc
