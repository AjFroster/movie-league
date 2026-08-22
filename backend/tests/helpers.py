"""Shared test helpers."""
from fastapi import HTTPException

from app import auth
from app.main import app


def act_as(user_id):
    """Sign subsequent requests as `user_id`; None means signed out.

    One definition. There were two, with different semantics -- test_visibility handled
    the signed-out case and test_auth did not -- so a test could pass because its author
    had the other version in mind. Both dependencies are overridden: read routes take the
    optional one, and overriding only `current_user` leaves reads resolving to the real
    local identity.
    """
    app.dependency_overrides[auth.current_user] = lambda: user_id
    app.dependency_overrides[auth.current_user_optional] = lambda: user_id
    if user_id is None:
        def _unauthenticated():
            raise HTTPException(status_code=401, detail="Sign in to do that.")
        app.dependency_overrides[auth.current_user] = _unauthenticated
