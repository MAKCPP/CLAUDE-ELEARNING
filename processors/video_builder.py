import subprocess
import os
from pathlib import Path
from typing import Callable


VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FRAMERATE = 25


def build_video(
    slide_images: list[str],
    audio_files: list[str],
    output_path: str,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> str:
    """Combine slide images with audio chunks into a single MP4 e-learning video.

    Each slide is displayed for the duration of its corresponding audio clip.
    Slides are scaled to fit 1920x1080 with letterbox/pillarbox as needed.
    Returns the path to the generated video.
    """
    output_path = Path(output_path)
    work_dir = output_path.parent / "segments"
    work_dir.mkdir(parents=True, exist_ok=True)

    segment_paths: list[str] = []
    total = len(slide_images)

    for i, (img, audio) in enumerate(zip(slide_images, audio_files)):
        if progress_cb:
            progress_cb(i, total, f"Encodage slide {i + 1}/{total}…")

        seg = str(work_dir / f"seg_{i:03d}.mp4")
        vf = (
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            f"force_original_aspect_ratio=decrease,"
            f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=#1e1e2e,"
            f"setsar=1"
        )
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", img,
                "-i", audio,
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-preset", "fast",
                "-crf", "20",
                "-vf", vf,
                "-r", str(FRAMERATE),
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-pix_fmt", "yuv420p",
                "-shortest",
                seg,
            ],
            capture_output=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg failed on segment {i}: {result.stderr.decode(errors='replace')}"
            )
        segment_paths.append(seg)

    if progress_cb:
        progress_cb(total, total, "Assemblage final…")

    concat_file = str(work_dir / "concat.txt")
    with open(concat_file, "w") as f:
        for seg in segment_paths:
            f.write(f"file '{seg}'\n")

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            str(output_path),
        ],
        capture_output=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg concat failed: {result.stderr.decode(errors='replace')}"
        )

    # Cleanup working files
    for seg in segment_paths:
        try:
            os.remove(seg)
        except OSError:
            pass
    try:
        os.remove(concat_file)
        work_dir.rmdir()
    except OSError:
        pass

    return str(output_path)
