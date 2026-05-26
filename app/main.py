from datetime import datetime

from fastapi import FastAPI

from app.routers import projects, stages, scans

app = FastAPI(
    title="BuildTrack Backend",
    description="Backend-модуль системы цифрового строительного контроля",
    version="1.0.0"
)


@app.get("/")
def root():
    return {
        "service": "BuildTrack Backend",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "BuildTrack Backend",
        "version": "1.0.0",
        "checked_at": datetime.utcnow()
    }


app.include_router(projects.router)
app.include_router(stages.router)
app.include_router(scans.router)