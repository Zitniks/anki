"""Page rendering router"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from settings import settings
from repositories import storage

router = APIRouter()
templates = Jinja2Templates(directory=str(settings.TEMPLATES_PATH))
templates.env.globals.update({"app_name": settings.APP_NAME})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Login / register page"""
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/", response_class=HTMLResponse)
async def root(request: Request) -> HTMLResponse:
    """Main page"""
    return templates.TemplateResponse("new_index.html", {"request": request})


@router.get("/materials", response_class=HTMLResponse)
async def materials(request: Request) -> HTMLResponse:
    """Materials page"""
    return templates.TemplateResponse("materials.html", {"request": request})


@router.get("/attachments", response_class=HTMLResponse)
async def attachments_page(request: Request) -> HTMLResponse:
    """Attachments page — global gallery of all uploaded files"""
    return templates.TemplateResponse("attachments.html", {"request": request})


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request) -> HTMLResponse:
    """Calendar page - global lesson calendar"""
    return templates.TemplateResponse("calendar.html", {"request": request})


@router.get("/repeat/{project_id}", response_class=HTMLResponse)
async def repeat_page(request: Request, project_id: str) -> HTMLResponse:
    """Repeat page — tests/quizzes/surveys for a student"""
    project = await storage.projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return templates.TemplateResponse("repeat.html", {"request": request, "project_id": project_id})


@router.get("/student/{project_id}", response_class=HTMLResponse)
async def student_profile(request: Request, project_id: str) -> HTMLResponse:
    """Student profile page"""
    # Verify project exists
    project = await storage.projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return templates.TemplateResponse("student_profile.html", {"request": request, "project_id": project_id})


@router.get("/{project_id}", response_class=HTMLResponse)
async def chat_page(request: Request, project_id: str) -> HTMLResponse:
    """Chat page"""
    # Verify project exists
    project = await storage.projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return templates.TemplateResponse("chat.html", {"request": request, "project_id": project_id})


@router.get("/lesson/{project_id}", response_class=HTMLResponse)
async def lesson_page(request: Request, project_id: str) -> HTMLResponse:
    # Verify project exists
    project = await storage.projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return templates.TemplateResponse("lesson.html", {"request": request, "project_id": project_id})
