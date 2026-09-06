from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
import hashlib
import json

from app import models, schemas
from app.core.time import utc_now
from app.core.enums import ProjectRole
from app.database import get_db
from app.services import auth_service

router = APIRouter(
    prefix="/projects",
    tags=["Проекты"],
    dependencies=[Depends(auth_service.get_current_user)],
)


def safe_get(obj, *field_names):
    
    if obj is None:
        return None

    for field_name in field_names:
        if hasattr(obj, field_name):
            return getattr(obj, field_name)

    return None


def get_object_datetime(obj):
    
    return safe_get(
        obj,
        "changed_at",
        "created_at",
        "updated_at",
        "timestamp",
        "checked_at"
    )


def generate_sha256_from_dict(data: dict) -> str:


    json_data = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        default=str
    )

    return hashlib.sha256(json_data.encode("utf-8")).hexdigest()


@router.post("/", response_model=schemas.ProjectResponse, summary="Создать проект")
def create_project(
    project: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    new_project = models.Project(
        name=project.name,
        description=project.description,
        location=project.location,
    )

    db.add(new_project)
    db.flush()
    if not current_user.is_system_admin:
        db.add(
            models.ProjectMembership(
                project_id=new_project.id,
                user_id=current_user.id,
                role=ProjectRole.PROJECT_MANAGER.value,
            )
        )
    db.commit()
    db.refresh(new_project)

    return new_project


@router.get("/", response_model=List[schemas.ProjectResponse], summary="Получить проекты")
def get_projects(
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    query = db.query(models.Project)
    accessible_ids = auth_service.accessible_project_ids(db, current_user)
    if accessible_ids is not None:
        query = query.filter(models.Project.id.in_(accessible_ids))
    projects = query.order_by(models.Project.id).all()
    return projects


@router.get("/{project_id}/report", summary="Получить сводку проекта")
def get_project_report(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    

    project = db.query(models.Project).filter(
        models.Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Объект не найден"
        )
    auth_service.ensure_project_roles(db, current_user, project_id)

    stages = db.query(models.Stage).filter(
        models.Stage.project_id == project_id
    ).all()

    scans = db.query(models.Scan).filter(
        models.Scan.project_id == project_id
    ).order_by(desc(models.Scan.id)).all()

    total_scans = len(scans)

    latest_scan = scans[0] if scans else None

    audit_logs = []

    for scan in scans:
        logs = db.query(models.ScanAuditLog).filter(
            models.ScanAuditLog.scan_id == scan.id
        ).order_by(desc(models.ScanAuditLog.id)).all()

        for log in logs:
            audit_logs.append({
                "audit_id": safe_get(log, "id"),
                "scan_id": safe_get(log, "scan_id"),
                "old_status": safe_get(log, "old_status"),
                "new_status": safe_get(log, "new_status"),
                "changed_by": safe_get(log, "changed_by"),
                "changed_at": get_object_datetime(log),
            })

    statuses = [
        safe_get(scan, "status")
        for scan in scans
    ]

    if not scans:
        final_status = "no_scans"
    elif "invalid" in statuses:
        final_status = "invalid"
    elif "manual_review" in statuses:
        final_status = "manual_review"
    elif all(status == "valid" for status in statuses):
        final_status = "valid"
    else:
        final_status = "pending"

    stages_data = []

    for stage in stages:
        stage_scans = [
            scan for scan in scans
            if safe_get(scan, "stage_id") == safe_get(stage, "id")
        ]

        stages_data.append({
            "stage_id": safe_get(stage, "id"),
            "stage_name": safe_get(stage, "name", "title"),
            "project_id": safe_get(stage, "project_id"),
            "scans_count": len(stage_scans),
            "scans": [
                {
                    "scan_id": safe_get(scan, "id"),
                    "file_name": safe_get(
                        scan,
                        "file_name",
                        "filename",
                        "original_filename",
                        "uploaded_filename"
                    ),
                    "file_path": safe_get(
                        scan,
                        "file_path",
                        "path",
                        "storage_path"
                    ),
                    "file_hash": safe_get(
                        scan,
                        "file_hash",
                        "sha256_hash",
                        "hash",
                        "checksum"
                    ),
                    "status": safe_get(scan, "status"),
                    "checked_by": safe_get(scan, "checked_by"),
                    "checked_at": safe_get(scan, "checked_at"),
                }
                for scan in stage_scans
            ]
        })

    latest_hash = None
    latest_status = None

    if latest_scan:
        latest_hash = safe_get(
            latest_scan,
            "file_hash",
            "sha256_hash",
            "hash",
            "checksum"
        )

        latest_status = safe_get(
            latest_scan,
            "status"
        )

    report = {
        "project": {
            "project_id": safe_get(project, "id"),
            "name": safe_get(project, "name", "title"),
            "description": safe_get(project, "description"),
        },
        "summary": {
            "total_stages": len(stages),
            "total_scans": total_scans,
            "latest_scan_id": safe_get(latest_scan, "id") if latest_scan else None,
            "latest_hash": latest_hash,
            "latest_status": latest_status,
            "final_object_status": final_status,
            "generated_at": utc_now(),
        },
        "stages": stages_data,
        "audit_trail": audit_logs
    }

    return report


@router.get(
    "/{project_id}/digital-proof",
    summary="Получить пакет проверки целостности",
)
def get_project_digital_proof(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    
    project = db.query(models.Project).filter(
        models.Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Объект не найден"
        )
    auth_service.ensure_project_roles(db, current_user, project_id)

    latest_scan = db.query(models.Scan).filter(
        models.Scan.project_id == project_id
    ).order_by(desc(models.Scan.id)).first()

    if not latest_scan:
        raise HTTPException(
            status_code=404,
            detail="У объекта пока нет загруженных сканов"
        )

    stage = db.query(models.Stage).filter(
        models.Stage.id == safe_get(latest_scan, "stage_id")
    ).first()

    proof_payload = {
        "project_id": safe_get(project, "id"),
        "project_name": safe_get(project, "name", "title"),
        "stage_id": safe_get(stage, "id"),
        "stage_name": safe_get(stage, "name", "title"),
        "scan_id": safe_get(latest_scan, "id"),
        "file_name": safe_get(
            latest_scan,
            "file_name",
            "filename",
            "original_filename",
            "uploaded_filename"
        ),
        "file_path": safe_get(
            latest_scan,
            "file_path",
            "path",
            "storage_path"
        ),
        "file_hash": safe_get(
            latest_scan,
            "file_hash",
            "sha256_hash",
            "hash",
            "checksum"
        ),
        "verification_status": safe_get(latest_scan, "status"),
        "checked_by": safe_get(latest_scan, "checked_by"),
        "checked_at": safe_get(latest_scan, "checked_at"),
        "algorithm": "SHA-256",
        "verification_method": "hash_based_integrity_check",
    }

    digital_proof_hash = generate_sha256_from_dict(proof_payload)
    proof_payload.update({
        "proof_generated_at": utc_now(),
        "external_registry_ready": False,
        "external_registry_status": "not_configured",
    })

    return {
        "message": "Пакет проверки целостности успешно сформирован",
        "proof_type": "Цифровое доказательство BuildTrack",
        "proof_payload": proof_payload,
        "digital_proof_hash": digital_proof_hash,
        "explanation": "Этот хеш является контрольным цифровым отпечатком результата проверки."
    }


@router.get(
    "/{project_id}",
    response_model=schemas.ProjectResponse,
    summary="Получить проект",
)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Объект не найден"
        )
    auth_service.ensure_project_roles(db, current_user, project_id)

    return project


@router.delete("/{project_id}", summary="Удалить проект")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Объект не найден"
        )
    auth_service.ensure_project_roles(
        db,
        current_user,
        project_id,
        {ProjectRole.PROJECT_MANAGER},
    )

    db.delete(project)
    db.commit()

    return {
        "message": "Объект удален",
        "project_id": project_id
    }
