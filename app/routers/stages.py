from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.enums import ProjectRole
from app.models import Project, Stage
from app.schemas import StageCreate, StageResponse
from app.services import auth_service

router = APIRouter(
    prefix="/stages",
    tags=["Этапы строительства"],
    dependencies=[Depends(auth_service.get_current_user)],
)


@router.post("/", response_model=StageResponse, summary="Создать этап строительства")
def create_stage(
    stage_data: StageCreate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    project = db.query(Project).filter(Project.id == stage_data.project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    auth_service.ensure_project_roles(
        db,
        current_user,
        stage_data.project_id,
        {ProjectRole.PROJECT_MANAGER},
    )

    stage = Stage(
        project_id=stage_data.project_id,
        name=stage_data.name,
        description=stage_data.description,
        status="pending",
    )

    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage


@router.get("/", response_model=List[StageResponse], summary="Получить этапы")
def get_stages(
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    query = db.query(Stage)
    accessible_ids = auth_service.accessible_project_ids(db, current_user)
    if accessible_ids is not None:
        query = query.filter(Stage.project_id.in_(accessible_ids))
    return query.order_by(Stage.id.desc()).all()


@router.get(
    "/project/{project_id}",
    response_model=List[StageResponse],
    summary="Получить этапы проекта",
)
def get_project_stages(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    auth_service.ensure_project_roles(db, current_user, project_id)

    return db.query(Stage).filter(Stage.project_id == project_id).order_by(Stage.id.desc()).all()


@router.get("/{stage_id}", response_model=StageResponse, summary="Получить этап")
def get_stage(
    stage_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    stage = db.query(Stage).filter(Stage.id == stage_id).first()

    if not stage:
        raise HTTPException(status_code=404, detail="Этап не найден")
    auth_service.ensure_project_roles(db, current_user, stage.project_id)

    return stage


@router.delete("/{stage_id}", summary="Удалить этап")
def delete_stage(
    stage_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    stage = db.query(Stage).filter(Stage.id == stage_id).first()

    if not stage:
        raise HTTPException(status_code=404, detail="Этап не найден")
    auth_service.ensure_project_roles(
        db,
        current_user,
        stage.project_id,
        {ProjectRole.PROJECT_MANAGER},
    )

    db.delete(stage)
    db.commit()

    return {"message": f"Этап {stage_id} успешно удалён"}
