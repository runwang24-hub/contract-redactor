import os
import threading
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote

from pydantic import BaseModel, Field

from app.desensitizer import Desensitizer, NullNerDetector
from app.document_redactor import DocumentRedactor
from app.ner import OnnxNerDetector
from app.serialization import result_to_dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "app" / "static"
WEB_RUNTIME_DIR = PROJECT_ROOT / "runtime" / "web-jobs"
ALLOWED_DOCUMENT_SUFFIXES = {".pdf", ".doc", ".docx"}
MAX_UPLOAD_BYTES = 60 * 1024 * 1024
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


class DesensitizeRequest(BaseModel):
    text: str = Field(min_length=1)
    mode: Literal["case_display", "contract_generation"] = "case_display"
    strict_level: Literal["low", "medium", "high"] = "medium"


class DesensitizeResponse(BaseModel):
    masked_text: str
    risk_level: str
    need_review: bool
    entities: list[dict]


@lru_cache(maxsize=1)
def get_desensitizer() -> Desensitizer:
    model_dir = os.getenv("NER_MODEL_DIR", "").strip()
    ner_detector = OnnxNerDetector(model_dir) if model_dir else NullNerDetector()
    return Desensitizer(ner_detector=ner_detector)


def create_app():
    try:
        from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise ImportError("Install API dependencies with: pip install -r requirements.txt") from exc

    app = FastAPI(title="Contract Redactor", version="0.2.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/desensitize", response_model=DesensitizeResponse)
    def desensitize(request: DesensitizeRequest) -> dict:
        result = get_desensitizer().desensitize(
            request.text,
            mode=request.mode,
            strict_level=request.strict_level,
        )
        return result_to_dict(result)

    @app.post("/api/jobs", status_code=202)
    async def create_document_job(
        request: Request,
        background_tasks: BackgroundTasks,
        x_filename: str = Header(default="contract.pdf"),
    ) -> dict[str, str]:
        filename = Path(unquote(x_filename).replace("\\", "/")).name
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_DOCUMENT_SUFFIXES:
            raise HTTPException(status_code=415, detail="仅支持 PDF、DOC 和 DOCX 文件")
        payload = await request.body()
        if not payload:
            raise HTTPException(status_code=400, detail="上传文件不能为空")
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="文件不能超过 60 MB")

        job_id = uuid.uuid4().hex
        job_dir = WEB_RUNTIME_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        input_path = job_dir / f"input{suffix}"
        output_path = job_dir / "redacted.pdf"
        input_path.write_bytes(payload)
        with JOBS_LOCK:
            JOBS[job_id] = {
                "id": job_id,
                "filename": filename,
                "status": "queued",
                "phase": "任务已创建",
                "progress": 2,
                "current_page": 0,
                "total_pages": 0,
                "summary": None,
                "error": None,
                "output_path": str(output_path),
            }
        background_tasks.add_task(
            _run_document_job,
            job_id,
            input_path,
            output_path,
            job_dir / "work",
        )
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}")
    def get_document_job(job_id: str) -> dict[str, Any]:
        job = _public_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在或服务已重启")
        return job

    @app.get("/api/jobs/{job_id}/preview", include_in_schema=False)
    def preview_document(job_id: str):
        output_path = _completed_output(job_id)
        if output_path is None:
            raise HTTPException(status_code=409, detail="任务尚未完成")
        return FileResponse(
            output_path,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline"},
        )

    @app.get("/api/jobs/{job_id}/download", include_in_schema=False)
    def download_document(job_id: str):
        output_path = _completed_output(job_id)
        if output_path is None:
            raise HTTPException(status_code=409, detail="任务尚未完成")
        job = _public_job(job_id) or {}
        original = Path(str(job.get("filename", "contract.pdf")))
        filename = f"{original.stem}-脱敏.pdf"
        return FileResponse(output_path, media_type="application/pdf", filename=filename)

    return app


def _run_document_job(
    job_id: str,
    input_path: Path,
    output_path: Path,
    work_dir: Path,
) -> None:
    _update_job(job_id, status="processing", phase="正在准备合同", progress=5)

    phase_names = {
        "prepare": "正在准备合同",
        "render": "正在生成页面图像",
        "ocr": "正在识别并脱敏",
        "export": "正在生成安全 PDF",
        "complete": "处理完成",
    }

    def report(stage: str, current: int, total: int) -> None:
        if stage == "prepare":
            progress = 5
        elif stage == "render":
            progress = 10
        elif stage == "ocr":
            progress = 14 + round(76 * current / max(total, 1))
        elif stage == "export":
            progress = 94
        else:
            progress = 100
        _update_job(
            job_id,
            status="processing" if stage != "complete" else "complete",
            phase=phase_names[stage],
            progress=progress,
            current_page=current,
            total_pages=total,
        )

    try:
        result = DocumentRedactor().process(
            input_path,
            output_path,
            work_dir=work_dir,
            dpi=200,
            progress_callback=report,
        )
        summary = {
            "pages": len(result.pages),
            "entities": sum(page.entity_count for page in result.pages),
            "stamps": sum(page.stamp_count for page in result.pages),
            "signature_fields": sum(page.signature_field_count for page in result.pages),
        }
        _update_job(
            job_id,
            status="complete",
            phase="处理完成",
            progress=100,
            summary=summary,
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            phase="处理失败",
            error=f"{type(exc).__name__}: {exc}",
        )


def _update_job(job_id: str, **values: Any) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(values)


def _public_job(job_id: str) -> dict[str, Any] | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        return {key: value for key, value in job.items() if key != "output_path"}


def _completed_output(job_id: str) -> Path | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job or job.get("status") != "complete":
            return None
        output_path = Path(str(job["output_path"]))
    return output_path if output_path.is_file() else None


app = create_app()
