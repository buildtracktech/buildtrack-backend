from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
import hashlib
import json

from app import models, schemas
from app.database import get_db

router = APIRouter(
    prefix="/projects",
    tags=["Projects"]
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


@router.post("/")
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    new_project = models.Project(
        name=project.name,
        description=project.description
    )

    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    return new_project


@router.get("/")
def get_projects(db: Session = Depends(get_db)):
    projects = db.query(models.Project).all()
    return projects


@router.get("/{project_id}/report")
def get_project_report(project_id: int, db: Session = Depends(get_db)):
    

    project = db.query(models.Project).filter(
        models.Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Объект не найден"
        )

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
            "generated_at": datetime.utcnow(),
        },
        "stages": stages_data,
        "audit_trail": audit_logs
    }

    return report


@router.get("/{project_id}/digital-proof")
def get_project_digital_proof(project_id: int, db: Session = Depends(get_db)):
    
    project = db.query(models.Project).filter(
        models.Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Объект не найден"
        )

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
        "proof_generated_at": datetime.utcnow(),
        "algorithm": "SHA-256",
        "verification_method": "hash_based_integrity_check",
        "external_registry_ready": True,
        "external_registry_status": "prepared"
    }

    digital_proof_hash = generate_sha256_from_dict(proof_payload)

    return {
        "message": "Digital proof package generated successfully",
        "proof_type": "BuildTrack Digital Proof",
        "proof_payload": proof_payload,
        "digital_proof_hash": digital_proof_hash,
        "explanation": "Этот хеш является контрольным цифровым отпечатком результата проверки."
    }


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(
        models.Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Объект не найден"
        )

    return project


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(
        models.Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Объект не найден"
        )

    db.delete(project)
    db.commit()

    return {
        "message": "Объект удален",
        "project_id": project_id
    }