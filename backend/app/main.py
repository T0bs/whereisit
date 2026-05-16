from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html

from .auth import auth_middleware
from .routers import ai as ai_router
from .routers import bulk as bulk_router
from .routers import embeddings as embeddings_router
from .routers import kinds as kinds_router
from .routers import nodes as nodes_router
from .routers import search as search_router
from .routers import tags as tags_router

app = FastAPI(title="whereisit")

app.middleware("http")(auth_middleware)
app.include_router(nodes_router.router)
app.include_router(tags_router.router)
app.include_router(kinds_router.router)
app.include_router(search_router.router)
app.include_router(ai_router.router)
app.include_router(embeddings_router.router)
app.include_router(bulk_router.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"ok": True, "app": "whereisit"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/swagger", response_class=HTMLResponse)
def swagger_ui():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="whereisit - Swagger UI")


@app.get("/redoc", response_class=HTMLResponse)
def redoc_ui():
    return get_redoc_html(openapi_url="/openapi.json", title="whereisit - ReDoc")
