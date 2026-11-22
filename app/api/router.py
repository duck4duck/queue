from fastapi import APIRouter, Depends
from app.api.auth import get_authenticated_tg_id
from app.api.v1.user_view import router as user_router
from app.api.v1.subject_view import router as subject_router
from app.api.v1.queue_view import router as queue_router
from app.api.v1.swap_view import router as swap_router
from app.api.v1.ws_view import router as ws_router
from app.api.v1.auth_view import router as auth_router


main_router = APIRouter()
main_router.include_router(user_router, dependencies=[Depends(get_authenticated_tg_id)])
main_router.include_router(subject_router)
main_router.include_router(queue_router, dependencies=[Depends(get_authenticated_tg_id)])
main_router.include_router(swap_router, dependencies=[Depends(get_authenticated_tg_id)])
main_router.include_router(ws_router)
main_router.include_router(auth_router)
