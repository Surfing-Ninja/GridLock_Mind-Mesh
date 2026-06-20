"""FastAPI application entrypoint for CurbFlow AI."""

from __future__ import annotations

import duckdb
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.dependencies import get_settings
from apps.api.routes import audit, blindspots, feedback, health, hotspots, metrics, patrol, planner, zones

OPENAPI_TAGS = [
    {"name": "health", "description": "Readiness and development diagnostics."},
    {"name": "audit", "description": "Dataset quality, evidence visibility, and bias audit summaries."},
    {"name": "zones", "description": "Zone GeoJSON and zone-level operational details."},
    {"name": "hotspots", "description": "Observed high-risk illegal-parking hotspot rankings."},
    {"name": "blindspots", "description": "Low-visibility, high-potential blindspot audit priorities."},
    {"name": "patrol", "description": "Aggregate patrol digital twin route and station summaries."},
    {"name": "planner", "description": "Resource-constrained enforcement plan recommendations."},
    {"name": "metrics", "description": "Model, baseline, and ranking metric summaries."},
    {"name": "feedback", "description": "Deployment feedback capture for future learning."},
]


def create_app() -> FastAPI:
    """Create and configure the CurbFlow AI FastAPI app."""

    settings = get_settings()
    app = FastAPI(
        title="CurbFlow AI",
        description=(
            "Bias-aware parking enforcement intelligence API. CurbFlow separates observed "
            "parking-risk signals from enforcement visibility gaps and never treats no challan "
            "as proof of no illegal parking."
        ),
        version=settings.app_version,
        openapi_tags=OPENAPI_TAGS,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$" if settings.is_development else None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    routers = [
        health.router,
        audit.router,
        zones.router,
        hotspots.router,
        blindspots.router,
        patrol.router,
        planner.router,
        metrics.router,
        feedback.router,
    ]
    for router in routers:
        app.include_router(router)
        app.include_router(router, prefix="/api", include_in_schema=False)

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": f"Invalid request: {exc}"})

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_handler(_: Request, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": f"Required CurbFlow artifact is missing: {exc}"},
        )

    @app.exception_handler(duckdb.Error)
    async def duckdb_error_handler(_: Request, exc: duckdb.Error) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "DuckDB query failed. Verify data/app/curbflow.duckdb has been seeded "
                    f"with `make db`. Underlying error: {exc}"
                )
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return app


app = create_app()
