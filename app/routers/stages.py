from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, Stage
from app.schemas import StageCreate, StageResponse

router = APIRouter(prefix="/stages", tags=["Stages"])


@router.post("/", response_model=StageResponse)
def create_stage(stage_data: StageCreate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == stage_data.project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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


@router.get("/", response_model=List[StageResponse])
def get_stages(db: Session = Depends(get_db)):
    return db.query(Stage).order_by(Stage.id.desc()).all()


@router.get("/project/{project_id}", response_model=List[StageResponse])
def get_project_stages(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return db.query(Stage).filter(Stage.project_id == project_id).order_by(Stage.id.desc()).all()

@router.delete("/{stage_id}")
def delete_stage(stage_id: int, db: Session = Depends(get_db)):
    stage = db.query(Stage).filter(Stage.id == stage_id).first()

    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    db.delete(stage)
    db.commit()

    return {"message": f"Stage {stage_id} deleted successfully"}