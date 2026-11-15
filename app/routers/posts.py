from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from app.routers.auth import COOKIE_NAME, validate_mutation
from app.schemas.posts import PostInput, PostText, PostDetail, PostList
from app.services import post_store, post_social_store
from app.schemas.post_social import CommentInput, CommentList, CommentMutation, CommentCount, LikeState

# 공개 조회도 같은 경로를 사용해 기존 인증 쿠키의 Path를 유지한다.
router = APIRouter(prefix="/api/auth/posts", tags=["posts"])


def run(response, operation, *args):
    response.headers["Cache-Control"] = "no-store"
    try:
        return operation(*args)
    except PermissionError as error:
        raise HTTPException(401, str(error)) from None
    except LookupError as error:
        raise HTTPException(404, str(error)) from None
    except ValidationError:
        raise HTTPException(422, "공유할 작품 데이터가 올바르지 않습니다.") from None


@router.get("", response_model=PostList)
def list_posts(response: Response, offset: int = Query(0, ge=0), limit: int = Query(12, ge=1, le=24)):
    return run(response, post_store.list_posts, offset, limit)


@router.get("/{post_id}", response_model=PostDetail)
def detail(post_id: str, request: Request, response: Response):
    return run(response, post_store.get, post_id, request.cookies.get(COOKIE_NAME))


@router.post("", response_model=PostDetail, status_code=201, dependencies=[Depends(validate_mutation)])
def create(payload: PostInput, request: Request, response: Response):
    return run(response, post_store.create, request.cookies.get(COOKIE_NAME), payload)


@router.patch("/{post_id}", response_model=PostDetail, dependencies=[Depends(validate_mutation)])
def edit(post_id: str, payload: PostText, request: Request, response: Response):
    return run(response, post_store.edit, request.cookies.get(COOKIE_NAME), post_id, payload)


@router.delete("/{post_id}", status_code=204, dependencies=[Depends(validate_mutation)])
def delete(post_id: str, request: Request, response: Response):
    run(response, post_store.delete, request.cookies.get(COOKIE_NAME), post_id)


@router.get("/{post_id}/comments", response_model=CommentList)
def comments(post_id: str, request: Request, response: Response, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=20)):
    return run(response, post_social_store.list_comments, post_id, request.cookies.get(COOKIE_NAME), offset, limit)


@router.post("/{post_id}/comments", response_model=CommentMutation, status_code=201, dependencies=[Depends(validate_mutation)])
def create_comment(post_id: str, payload: CommentInput, request: Request, response: Response):
    return run(response, post_social_store.create_comment, request.cookies.get(COOKIE_NAME), post_id, payload.content)


@router.patch("/{post_id}/comments/{comment_id}", response_model=CommentMutation, dependencies=[Depends(validate_mutation)])
def edit_comment(post_id: str, comment_id: str, payload: CommentInput, request: Request, response: Response):
    return run(response, post_social_store.edit_comment, request.cookies.get(COOKIE_NAME), post_id, comment_id, payload.content)


@router.delete("/{post_id}/comments/{comment_id}", response_model=CommentCount, dependencies=[Depends(validate_mutation)])
def delete_comment(post_id: str, comment_id: str, request: Request, response: Response):
    return run(response, post_social_store.delete_comment, request.cookies.get(COOKIE_NAME), post_id, comment_id)


@router.put("/{post_id}/like", response_model=LikeState, dependencies=[Depends(validate_mutation)])
def like(post_id: str, request: Request, response: Response):
    return run(response, post_social_store.set_like, request.cookies.get(COOKIE_NAME), post_id, True)


@router.delete("/{post_id}/like", response_model=LikeState, dependencies=[Depends(validate_mutation)])
def unlike(post_id: str, request: Request, response: Response):
    return run(response, post_social_store.set_like, request.cookies.get(COOKIE_NAME), post_id, False)
