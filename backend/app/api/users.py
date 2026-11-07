from __future__ import annotations

from flask import Blueprint

from ..auth import generate_token, hash_token
from ..errors import ApiError
from ..repo import users as users_repo
from ..schemas.users import CreateUserRequest, CreateUserResponse
from .params import body

bp = Blueprint("users", __name__)


@bp.post("/users")
def create_user():
    req = CreateUserRequest.model_validate(body())
    token = generate_token()
    try:
        user = users_repo.create(req.username, hash_token(token))
    except users_repo.UsernameTaken as e:
        raise ApiError(409, "username_taken", f"Username '{req.username}' is already taken") from e
    resp = CreateUserResponse(user_id=user["id"], username=user["username"], token=token)
    return resp.model_dump(mode="json"), 201
