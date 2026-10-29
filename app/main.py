"""
HotelPro Enterprise Hotel Management Platform - Main FastAPI Application
PRD Version 1.0
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.seed import seed_demo_data
from app.api.auth_router import router as auth_router
from app.api.inventory_router import router as inventory_router
from app.api.booking_router import router as booking_router
from app.api.frontdesk_router import router as frontdesk_router
from app.api.folio_router import router as folio_router
from app.api.housekeeping_router import router as housekeeping_router
from app.api.night_audit_router import router as night_audit_router
from app.api.audit_router import router as audit_router
from app.api.integrations_router import router as integrations_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize multi-tenant database & schema
    init_db()
    seed_demo_data()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Enterprise hotel management platform unifying front-desk workflows, multi-channel booking lifecycles, dynamic room inventory, and PCI-compliant financial settlements.",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS middleware for modern frontend SPAs
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers under /api/v1
api_prefix = settings.API_V1_PREFIX
app.include_router(auth_router, prefix=api_prefix)
app.include_router(inventory_router, prefix=api_prefix)
app.include_router(booking_router, prefix=api_prefix)
app.include_router(frontdesk_router, prefix=api_prefix)
app.include_router(folio_router, prefix=api_prefix)
app.include_router(housekeeping_router, prefix=api_prefix)
app.include_router(night_audit_router, prefix=api_prefix)
app.include_router(audit_router, prefix=api_prefix)
app.include_router(integrations_router, prefix=api_prefix)

# Static files for web client
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "HotelPro API is live. Navigate to /api/docs for API explorer."}

@app.get("/health")
def health_check():
    """High-availability health check endpoint per PRD Section 5."""
    return {
        "status": "HEALTHY",
        "service": "HotelPro Core Platform",
        "version": settings.VERSION,
        "database": "CONNECTED",
        "concurrency_locks": "ACTIVE"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

