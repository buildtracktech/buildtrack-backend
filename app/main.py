from fastapi import FastAPI

from app.core.time import utc_now
from app.routers import acts, auth, checks, documents, normatives, projects, scans, stages, tasks, users

app = FastAPI(
    title="BuildTrack Backend",
    description="Backend-модуль системы цифрового строительного контроля",
    version="1.0.0"
)


@app.get("/", tags=["Система"], summary="Получить сведения о сервисе")
def root():
    return {
        "service": "BuildTrack Backend",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health", tags=["Система"], summary="Проверить состояние сервиса")
def health_check():
    return {
        "status": "ok",
        "service": "BuildTrack Backend",
        "version": "1.0.0",
        "checked_at": utc_now()
    }


app.include_router(projects.router)
app.include_router(auth.router)
app.include_router(stages.router)
app.include_router(scans.router)
app.include_router(normatives.router)
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(documents.router)
app.include_router(checks.router)
app.include_router(acts.router)
