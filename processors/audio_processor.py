import subprocess
import json
from pathlib import Path


def get_audio_duration(audio_path: str) -> float:
    """Return duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    data = json.loads(result.stdout)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            return float(stream.get("duration", 0))
    # Fallback: use format duration
    result2 = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    data2 = json.loads(result2.stdout)
    return float(data2.get("format", {}).get("duration", 0))


def split_audio_by_word_proportions(
    audio_path: str,
    segments: list[str],
    output_dir: str,
) -> tuple[list[str], list[float]]:
    """Split a single audio file into one chunk per segment.

    The split is proportional to the word count of each segment.
    Returns (list_of_wav_paths, list_of_durations_seconds).
    """
    total_duration = get_audio_duration(audio_path)
    if total_duration <= 0:
        raise RuntimeError("Cannot determine audio duration.")

    word_counts = [max(1, len(s.split())) for s in segments]
    total_words = sum(word_counts)
    durations = [total_duration * (wc / total_words) for wc in word_counts]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_files: list[str] = []
    current_time = 0.0

    for i, duration in enumerate(durations):
        out_file = str(output_dir / f"audio_{i:03d}.wav")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(audio_path),
                "-ss", f"{current_time:.3f}",
                "-t", f"{duration:.3f}",
                "-c:a", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                out_file,
            ],
            capture_output=True,
            timeout=120,
        )
        audio_files.append(out_file)
        current_time += duration

    return audio_files, durations
