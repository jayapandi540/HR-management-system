from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from ..schemas import ResumeUploadResponse
from ..deps import get_db
from ats_system.orm.models import Resume
from doc_pipeline.pipeline import run_pipeline_and_store
import uuid

router = APIRouter()

@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(file: UploadFile = File(...), db=Depends(get_db)):
    external_id = str(uuid.uuid4())
    # Save file temporarily
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    # Run pipeline
    result = run_pipeline_and_store(tmp_path, external_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    # Store resume ID in main ORM
    resume = Resume(
        id=external_id,
        external_id=external_id,
        masked_json=result.masked_json,
        pii_json=result.pii_json,
        status="completed"
    )
    db.add(resume)
    db.commit()
    return {"id": external_id, "status": "completed"}