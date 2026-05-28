import asyncio
import os
import shutil
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from processors.audio_processor import split_audio_by_word_proportions
from processors.llm_processor import ALL_MODELS, segment_text_by_slides
from processors.pptx_processor import convert_pptx_to_images, extract_slide_texts
from processors.video_builder import build_video

BASE_DIR = Path(__file__).parent
JOBS_DIR = BASE_DIR / "jobs"
JOBS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="ELearning Video Generator")

# In-memory job registry: job_id → status dict
jobs: dict[str, dict[str, Any]] = {}


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def _update(job_id: str, **kwargs: Any) -> None:
    jobs[job_id].update(kwargs)


async def _save_upload(upload: UploadFile, dest: Path) -> None:
    async with aiofiles.open(dest, "wb") as f:
        while chunk := await upload.read(1024 * 256):
            await f.write(chunk)


def _decode_text(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Cannot decode text file — unsupported encoding.")


# ─────────────────────────────────────────────
# Background processing pipeline
# ─────────────────────────────────────────────

def _run_pipeline(job_id: str, job_dir: Path, llm_model: str, api_key: str) -> None:
    try:
        def step(pct: int, msg: str) -> None:
            _update(job_id, progress=pct, message=msg)

        step(2, "Lecture des fichiers…")

        audio_path = next(job_dir.glob("audio.*"))
        text_path = next(job_dir.glob("text.*"))
        pptx_path = next(job_dir.glob("pptx.*"))

        narration = _decode_text(text_path)
        if not narration.strip():
            raise ValueError("Le fichier texte est vide.")

        step(8, "Conversion des slides en images…")
        images_dir = job_dir / "images"
        slide_images = convert_pptx_to_images(str(pptx_path), str(images_dir))

        n_slides = len(slide_images)
        if n_slides == 0:
            raise ValueError("Aucune slide trouvée dans la présentation.")

        step(20, f"{n_slides} slides extraites — analyse du texte par le LLM…")
        slide_infos = extract_slide_texts(str(pptx_path))

        # Ensure slide_infos length matches images (LibreOffice may differ from python-pptx count)
        if len(slide_infos) != n_slides:
            slide_infos = [
                {"slide_number": i + 1, "title": f"Slide {i + 1}", "content": ""}
                for i in range(n_slides)
            ]

        step(30, "Segmentation du texte par slide (LLM)…")
        segments = segment_text_by_slides(narration, slide_infos, llm_model, api_key)

        if len(segments) != n_slides:
            raise ValueError(
                f"Le LLM a retourné {len(segments)} segments pour {n_slides} slides."
            )

        step(50, "Découpage de l'audio…")
        audio_dir = job_dir / "audio_chunks"
        audio_files, durations = split_audio_by_word_proportions(
            str(audio_path), segments, str(audio_dir)
        )

        step(60, "Génération de la vidéo…")
        output_path = job_dir / "elearning.mp4"

        def video_progress(current: int, total: int, msg: str) -> None:
            pct = 60 + int(35 * current / max(total, 1))
            _update(job_id, progress=pct, message=msg)

        build_video(slide_images, audio_files, str(output_path), video_progress)

        _update(
            job_id,
            status="done",
            progress=100,
            message="Vidéo générée avec succès !",
            output_path=str(output_path),
            n_slides=n_slides,
            duration_total=round(sum(durations), 1),
        )

    except Exception as exc:
        _update(
            job_id,
            status="error",
            progress=0,
            message=str(exc),
            detail=traceback.format_exc(),
        )


# ─────────────────────────────────────────────
# API routes
# ─────────────────────────────────────────────

@app.get("/api/models")
def list_models() -> dict:
    return {"models": [{"id": k, "label": v} for k, v in ALL_MODELS.items()]}


@app.post("/api/process")
async def start_processing(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    text: UploadFile = File(...),
    pptx: UploadFile = File(...),
    llm_model: str = Form(...),
    api_key: str = Form(...),
) -> dict:
    # Basic validation
    if not api_key.strip():
        raise HTTPException(status_code=400, detail="API key is required.")
    if llm_model not in ALL_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {llm_model}")

    audio_ext = Path(audio.filename or "audio.mp3").suffix.lower() or ".mp3"
    text_ext = Path(text.filename or "text.txt").suffix.lower() or ".txt"
    pptx_ext = Path(pptx.filename or "pptx.pptx").suffix.lower() or ".pptx"

    allowed_audio = {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac", ".wma"}
    allowed_pptx = {".pptx", ".ppt", ".odp"}

    if audio_ext not in allowed_audio:
        raise HTTPException(status_code=400, detail=f"Format audio non supporté : {audio_ext}")
    if pptx_ext not in allowed_pptx:
        raise HTTPException(status_code=400, detail=f"Format présentation non supporté : {pptx_ext}")

    job_id = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True)

    await _save_upload(audio, job_dir / f"audio{audio_ext}")
    await _save_upload(text, job_dir / f"text{text_ext}")
    await _save_upload(pptx, job_dir / f"pptx{pptx_ext}")

    jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "message": "Démarrage du traitement…",
        "created_at": time.time(),
    }

    background_tasks.add_task(_run_pipeline, job_id, job_dir, llm_model, api_key)
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def get_status(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job introuvable.")
    return jobs[job_id]


@app.get("/api/download/{job_id}")
def download_video(job_id: str) -> FileResponse:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job introuvable.")
    job = jobs[job_id]
    if job.get("status") != "done":
        raise HTTPException(status_code=400, detail="La vidéo n'est pas encore prête.")
    output = Path(job["output_path"])
    if not output.exists():
        raise HTTPException(status_code=404, detail="Fichier vidéo introuvable sur le serveur.")
    return FileResponse(
        str(output),
        media_type="video/mp4",
        filename="elearning.mp4",
        headers={"Content-Disposition": 'attachment; filename="elearning.mp4"'},
    )


@app.delete("/api/job/{job_id}")
def delete_job(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job introuvable.")
    job_dir = JOBS_DIR / job_id
    shutil.rmtree(job_dir, ignore_errors=True)
    jobs.pop(job_id, None)
    return {"deleted": job_id}


# ─────────────────────────────────────────────
# Serve frontend
# ─────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(BASE_DIR / "static" / "index.html"))
