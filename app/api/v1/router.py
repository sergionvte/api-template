"""Router de la versión v1. `apigen` registra aquí los recursos nuevos."""

from fastapi import APIRouter

from app.api.v1.endpoints import account, auth, jobs, users

# [apigen:imports]

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(account.router)
api_router.include_router(users.router)
api_router.include_router(jobs.router)
# [apigen:routers]
