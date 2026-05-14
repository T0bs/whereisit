from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html

from .auth import auth_middleware
from .database import engine
from .models import Base

from .routers import items as items_router
from .routers import containers as containers_router
from .routers import placements as placements_router
from .routers import tags as tags_router
from .routers import views as views_router

app = FastAPI(title="whereisit")

app.middleware("http")(auth_middleware)

# Enable CORS for browser-based Swagger testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    # Create tables for quick local development (Alembic is recommended for prod)
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"ok": True, "app": "whereisit"}


@app.get("/health")
def health():
    return {"status": "healthy"}


app.include_router(items_router.router)
app.include_router(containers_router.router)
app.include_router(placements_router.router)
app.include_router(tags_router.router)
app.include_router(views_router.router)


@app.get("/swagger", response_class=HTMLResponse)
def swagger_ui():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="whereisit - Swagger UI")


@app.get("/redoc", response_class=HTMLResponse)
def redoc_ui():
    return get_redoc_html(openapi_url="/openapi.json", title="whereisit - ReDoc")
