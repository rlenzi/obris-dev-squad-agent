"""FastAPI app principal do Control Plane.

Inclui todos os routers (auth, me, health, webhooks, futuros admin/client).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dev_autonomo.config import get_settings
from dev_autonomo.control_plane import webhooks as webhooks_module
from dev_autonomo.control_plane.routers import admin_clients as admin_clients_router
from dev_autonomo.control_plane.routers import admin_credentials as admin_credentials_router
from dev_autonomo.control_plane.routers import admin_stack_knowledge as admin_stack_knowledge_router
from dev_autonomo.control_plane.routers import admin_users as admin_users_router
from dev_autonomo.control_plane.routers import auth as auth_router
from dev_autonomo.control_plane.routers import client_agent_runs as client_agent_runs_router
from dev_autonomo.control_plane.routers import client_credentials as client_credentials_router
from dev_autonomo.control_plane.routers import client_skill_proposer as client_skill_proposer_router
from dev_autonomo.control_plane.routers import client_squad_knowledge as client_squad_knowledge_router
from dev_autonomo.control_plane.routers import client_squads as client_squads_router
from dev_autonomo.control_plane.routers import client_users as client_users_router
from dev_autonomo.control_plane.routers import cost as cost_router
from dev_autonomo.control_plane.routers import health as health_router
from dev_autonomo.control_plane.routers import me as me_router
from dev_autonomo.control_plane.routers import skill_templates as skill_templates_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gerencia o ciclo de vida do app: captura o instante de startup."""
    health_router.set_startup_time()
    logger.info("Backend startup registrado (uptime clock iniciado).")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="dev-autonomo Control Plane",
        version="0.2.0",
        description="API multi-tenant que serve admin e client portals.",
        lifespan=lifespan,
    )

    # CORS para os dois painéis (admin.* e app.*). Em dev, aceita localhost.
    allowed_origins = (
        ["*"]
        if settings.ENVIRONMENT == "local"
        else [
            "https://admin.dev-autonomo.com",
            "https://app.dev-autonomo.com",
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(me_router.router)
    app.include_router(admin_clients_router.router)
    app.include_router(admin_credentials_router.router)
    app.include_router(admin_stack_knowledge_router.router)
    app.include_router(admin_users_router.router)
    app.include_router(client_squads_router.router)
    app.include_router(client_squad_knowledge_router.router)
    app.include_router(client_users_router.router)
    app.include_router(client_credentials_router.router)
    app.include_router(skill_templates_router.router)
    app.include_router(client_skill_proposer_router.router)
    app.include_router(cost_router.admin_router)
    app.include_router(cost_router.client_router)
    app.include_router(client_agent_runs_router.router)

    # Webhooks: monta sob /webhooks
    # webhooks.py expoe `app` FastAPI proprio; pegamos as rotas dele
    for route in webhooks_module.app.routes:
        if hasattr(route, "endpoint"):
            app.add_api_route(
                route.path,
                route.endpoint,
                methods=list(route.methods or set()),
                name=route.name,
            )

    return app


app = create_app()
