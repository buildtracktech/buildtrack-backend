import shutil
from pathlib import Path
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import ProjectRole
from app.core.time import utc_now
from app.database import get_db
from app.models import Project, Scan, ScanAuditLog, Stage
from app.schemas import ScanAuditLogResponse, ScanResponse, ScanStatusUpdate
from app.services.hash_service import calculate_sha256
from app.services import auth_service

router = APIRouter(
    prefix="/scans",
    tags=["Сканы"],
    dependencies=[Depends(auth_service.get_current_user)],
)

ALLOWED_STATUSES = {"pending", "valid", "invalid", "manual_review"}


@router.post("/upload", response_model=ScanResponse, summary="Загрузить скан")
def upload_scan(
    project_id: int = Form(...),
    stage_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    auth_service.ensure_project_roles(
        db,
        current_user,
        project_id,
        {
            ProjectRole.PROJECT_MANAGER,
            ProjectRole.INSPECTOR,
            ProjectRole.SERVICE_AGENT,
        },
    )

    stage = db.query(Stage).filter(Stage.id == stage_id, Stage.project_id == project_id).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Этап не найден в этом проекте")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Не указано имя файла")

    file_extension = Path(file.filename).suffix
    stored_filename = f"{uuid4().hex}{file_extension}"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    physical_file_path = settings.upload_dir / stored_filename
    storage_path = Path("uploads") / stored_filename

    try:
        with physical_file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        file_hash = calculate_sha256(str(physical_file_path))
    except OSError as exc:
        physical_file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Не удалось сохранить загруженный скан") from exc

    try:
        scan = Scan(
            project_id=project_id,
            stage_id=stage_id,
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_path=str(storage_path),
            file_hash=file_hash,
            status="pending",
            comment="Скан загружен, контрольная сумма SHA-256 рассчитана",
        )

        db.add(scan)
        db.flush()

        audit_log = ScanAuditLog(
            scan_id=scan.id,
            old_status=None,
            new_status="pending",
            comment="Первичная загрузка",
            changed_by="система",
        )

        db.add(audit_log)
        db.commit()
        db.refresh(scan)
    except SQLAlchemyError as exc:
        db.rollback()
        physical_file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Не удалось сохранить сведения о скане") from exc

    return scan


@router.patch(
    "/{scan_id}/status",
    response_model=ScanResponse,
    summary="Изменить статус скана",
)
def update_scan_status(
    scan_id: int,
    status_data: ScanStatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()

    if not scan:
        raise HTTPException(status_code=404, detail="Скан не найден")
    auth_service.ensure_project_roles(
        db,
        current_user,
        scan.project_id,
        {ProjectRole.PROJECT_MANAGER, ProjectRole.INSPECTOR},
    )

    if status_data.status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Некорректный статус. Допустимые значения: {', '.join(ALLOWED_STATUSES)}"
        )

    old_status = scan.status

    scan.status = status_data.status
    scan.comment = status_data.comment
    scan.checked_by = current_user.email
    scan.checked_at = utc_now()

    stage = db.query(Stage).filter(Stage.id == scan.stage_id).first()
    if stage:
        stage.status = status_data.status

    audit_log = ScanAuditLog(
        scan_id=scan.id,
        old_status=old_status,
        new_status=status_data.status,
        comment=status_data.comment,
        changed_by=current_user.email,
    )

    db.add(audit_log)
    try:
        db.commit()
        db.refresh(scan)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Не удалось обновить статус скана") from exc

    return scan


@router.get("/", response_model=List[ScanResponse], summary="Получить сканы")
def get_scans(
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    query = db.query(Scan)
    accessible_ids = auth_service.accessible_project_ids(db, current_user)
    if accessible_ids is not None:
        query = query.filter(Scan.project_id.in_(accessible_ids))
    return query.order_by(Scan.id.desc()).all()


@router.get("/{scan_id}", response_model=ScanResponse, summary="Получить скан")
def get_scan(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()

    if not scan:
        raise HTTPException(status_code=404, detail="Скан не найден")
    auth_service.ensure_project_roles(db, current_user, scan.project_id)

    return scan


@router.get(
    "/project/{project_id}",
    response_model=List[ScanResponse],
    summary="Получить сканы проекта",
)
def get_project_scans(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    auth_service.ensure_project_roles(db, current_user, project_id)

    return db.query(Scan).filter(Scan.project_id == project_id).order_by(Scan.id.desc()).all()


@router.get(
    "/stage/{stage_id}",
    response_model=List[ScanResponse],
    summary="Получить сканы этапа",
)
def get_stage_scans(
    stage_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    stage = db.query(Stage).filter(Stage.id == stage_id).first()

    if not stage:
        raise HTTPException(status_code=404, detail="Этап не найден")
    auth_service.ensure_project_roles(db, current_user, stage.project_id)

    return db.query(Scan).filter(Scan.stage_id == stage_id).order_by(Scan.id.desc()).all()


@router.get(
    "/{scan_id}/audit",
    response_model=List[ScanAuditLogResponse],
    summary="Получить историю скана",
)
def get_scan_audit(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()

    if not scan:
        raise HTTPException(status_code=404, detail="Скан не найден")
    auth_service.ensure_project_roles(db, current_user, scan.project_id)

    return db.query(ScanAuditLog).filter(ScanAuditLog.scan_id == scan_id).order_by(ScanAuditLog.id.desc()).all()


@router.delete("/{scan_id}", summary="Удалить скан")
def delete_scan(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()

    if not scan:
        raise HTTPException(status_code=404, detail="Скан не найден")
    auth_service.ensure_project_roles(
        db,
        current_user,
        scan.project_id,
        {ProjectRole.PROJECT_MANAGER},
    )

    file_path = settings.upload_dir / scan.stored_filename
    if not file_path.exists():
        file_path = Path(scan.file_path)
    if file_path.exists():
        file_path.unlink()

    db.delete(scan)
    db.commit()

    return {"message": f"Скан {scan_id} успешно удалён"}
