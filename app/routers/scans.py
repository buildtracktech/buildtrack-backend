import shutil
from datetime import datetime
from pathlib import Path
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, Scan, ScanAuditLog, Stage
from app.schemas import ScanAuditLogResponse, ScanResponse, ScanStatusUpdate
from app.services.hash_service import calculate_sha256

router = APIRouter(prefix="/scans", tags=["Scans"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_STATUSES = {"pending", "valid", "invalid", "manual_review"}


@router.post("/upload", response_model=ScanResponse)
def upload_scan(
    project_id: int = Form(...),
    stage_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    stage = db.query(Stage).filter(Stage.id == stage_id, Stage.project_id == project_id).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found for this project")

    file_extension = Path(file.filename).suffix
    stored_filename = f"{uuid4().hex}{file_extension}"
    file_path = UPLOAD_DIR / stored_filename

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_hash = calculate_sha256(str(file_path))

    scan = Scan(
        project_id=project_id,
        stage_id=stage_id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        file_path=str(file_path),
        file_hash=file_hash,
        status="pending",
        comment="Scan uploaded and SHA-256 hash calculated",
    )

    db.add(scan)
    db.commit()
    db.refresh(scan)

    audit_log = ScanAuditLog(
        scan_id=scan.id,
        old_status=None,
        new_status="pending",
        comment="Initial upload",
        changed_by="system",
    )

    db.add(audit_log)
    db.commit()

    return scan


@router.patch("/{scan_id}/status", response_model=ScanResponse)
def update_scan_status(scan_id: int, status_data: ScanStatusUpdate, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    if status_data.status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed statuses: {', '.join(ALLOWED_STATUSES)}"
        )

    old_status = scan.status

    scan.status = status_data.status
    scan.comment = status_data.comment
    scan.checked_by = status_data.checked_by
    scan.checked_at = datetime.utcnow()

    stage = db.query(Stage).filter(Stage.id == scan.stage_id).first()
    if stage:
        stage.status = status_data.status

    db.commit()
    db.refresh(scan)

    audit_log = ScanAuditLog(
        scan_id=scan.id,
        old_status=old_status,
        new_status=status_data.status,
        comment=status_data.comment,
        changed_by=status_data.checked_by,
    )

    db.add(audit_log)
    db.commit()

    return scan


@router.get("/", response_model=List[ScanResponse])
def get_scans(db: Session = Depends(get_db)):
    return db.query(Scan).order_by(Scan.id.desc()).all()


@router.get("/{scan_id}", response_model=ScanResponse)
def get_scan(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    return scan


@router.get("/project/{project_id}", response_model=List[ScanResponse])
def get_project_scans(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return db.query(Scan).filter(Scan.project_id == project_id).order_by(Scan.id.desc()).all()


@router.get("/stage/{stage_id}", response_model=List[ScanResponse])
def get_stage_scans(stage_id: int, db: Session = Depends(get_db)):
    stage = db.query(Stage).filter(Stage.id == stage_id).first()

    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    return db.query(Scan).filter(Scan.stage_id == stage_id).order_by(Scan.id.desc()).all()


@router.get("/{scan_id}/audit", response_model=List[ScanAuditLogResponse])
def get_scan_audit(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    return db.query(ScanAuditLog).filter(ScanAuditLog.scan_id == scan_id).order_by(ScanAuditLog.id.desc()).all()


@router.delete("/{scan_id}")
def delete_scan(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    file_path = Path(scan.file_path)
    if file_path.exists():
        file_path.unlink()

    db.delete(scan)
    db.commit()

    return {"message": f"Scan {scan_id} deleted successfully"}