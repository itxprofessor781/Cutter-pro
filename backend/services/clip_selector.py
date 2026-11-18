
import json
import re
import httpx

from config import settings


class ClipSelectionError(Exception):
    """Raised when AI clip selection fails."""


def _extract_json(text: str) -> dict:
    """Extract JSON returned by an AI model."""

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise ClipSelectionError(
            "AI did not return valid JSON."
        )

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ClipSelectionError(
            "AI returned malformed JSON."
        ) from exc


def select_viral_clips(
    transcript: dict,
    number_of_clips: int = 5,
    min_duration: int = 15,
    max_duration: int = 60,
) -> dict:
    """
    Ask Ollama to identify engaging moments in a transcript.

    Transcript must contain timestamped segments.
    """

    if not 1 <= number_of_clips <= 20:
        raise ClipSelectionError(
            "Number of clips must be between 1 and 20."
        )

    if min_duration < 5 or max_duration < min_duration:
        raise ClipSelectionError("Invalid clip duration settings.")

    segments = transcript.get("segments", [])

    if not segments:
        raise ClipSelectionError(
            "Transcript contains no timestamped segments."
        )

    total_duration = float(transcript.get("duration", 0))

    if total_duration <= 0:
        total_duration = max(
            float(segment.get("end", 0))
            for segment in segments
        )

    if total_duration <= 0:
        raise ClipSelectionError(
            "Could not determine transcript duration."
        )

    compact_segments = []

    for segment in segments:
        compact_segments.append({
            "start": float(segment.get("start", 0)),
            "end": float(segment.get("end", 0)),
            "text": str(segment.get("text", ""))[:1000],
        })

    prompt = f"""
You are an expert short-form video editor.

Analyze this timestamped transcript and find the most engaging
moments suitable for TikTok, Instagram Reels and YouTube Shorts.

Choose up to {number_of_clips} different clips.

Rules:
- Each clip must be between {min_duration} and {max_duration} seconds.
- Use only timestamps inside the supplied transcript.
- Prefer strong hooks, surprising facts, useful advice,
  emotional moments, humor, debates and complete thoughts.
- Avoid long introductions, silence and incomplete sentences.
- Do not invent dialogue or events.
- Avoid overlapping clips when possible.
- Return ONLY valid JSON. No Markdown.

Required JSON format:
{{
  "clips": [
    {{
      "start": 10.0,
      "end": 40.0,
      "title": "Interesting short title",
      "reason": "Why this moment is engaging",
      "hook": "Opening hook",
      "score": 90
    }}
  ]
}}

Video duration: {total_duration}

Transcript:
{json.dumps(compact_segments, ensure_ascii=False)}
"""

    url = settings.OLLAMA_URL.rstrip("/") + "/api/chat"

    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You select engaging video clips. "
                    "Return valid JSON only."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.2,
        },
    }

    try:
        response = httpx.post(
            url,
            json=payload,
            timeout=300.0,
        )

        response.raise_for_status()

        response_data = response.json()
        message = response_data.get("message", {})
        ai_text = message.get("content", "")

        if not ai_text:
            raise ClipSelectionError(
                "Ollama returned an empty response."
            )

        result = _extract_json(ai_text)

    except httpx.HTTPError as exc:
        raise ClipSelectionError(
            f"Could not connect to Ollama: {exc}"
        ) from exc

    clips = result.get("clips", [])

    if not isinstance(clips, list):
        raise ClipSelectionError(
            "AI response has an invalid clips field."
        )

    valid_clips = []

    for clip in clips:
        try:
            start = float(clip["start"])
            end = float(clip["end"])
        except (KeyError, TypeError, ValueError):
            continue

        duration = end - start

        if start < 0 or end > total_duration:
            continue

        if duration < min_duration or duration > max_duration:
            continue

        try:
            score = int(clip.get("score", 50))
        except (ValueError, TypeError):
            score = 50

        valid_clips.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "duration": round(duration, 2),
            "title": str(clip.get("title", "Untitled clip"))[:120],
            "reason": str(clip.get("reason", ""))[:500],
            "hook": str(clip.get("hook", ""))[:250],
            "score": max(0, min(100, score)),
        })

    valid_clips.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return {
        "success": True,
        "total_clips": len(valid_clips),
        "clips": valid_clips[:number_of_clips],
        "ai_model": settings.OLLAMA_MODEL,
    }
