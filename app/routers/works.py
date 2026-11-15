from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.routers.auth import COOKIE_NAME, validate_mutation
from app.schemas.works import WorkInput, WorkSummary, WorkDetail
from app.services import work_store

router = APIRouter(prefix="/api/auth/works", tags=["works"])


def run(request, response, operation, *args):
    response.headers["Cache-Control"] = "no-store"
    try:
        return operation(request.cookies.get(COOKIE_NAME), *args)
    except PermissionError as error:
        raise HTTPException(401, str(error)) from None
    except LookupError as error:
        raise HTTPException(404, str(error)) from None


@router.post("", response_model=WorkSummary, status_code=201, dependencies=[Depends(validate_mutation)])
def save_work(payload: WorkInput, request: Request, response: Response):
    return run(request, response, work_store.save, payload)


@router.get("", response_model=list[WorkSummary])
def list_works(request: Request, response: Response):
    return run(request, response, work_store.list_works)


@router.get("/{work_id}", response_model=WorkDetail)
def get_work(work_id: str, request: Request, response: Response):
    return run(request, response, work_store.get_work, work_id)
