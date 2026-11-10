"""Domain errors to application/problem+json (RFC 0004 section 6). The only HTTP mapping."""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from opengrc import errors

STATUS: dict[type[errors.OpenGRCError], HTTPStatus] = {
    errors.Invalid: HTTPStatus.BAD_REQUEST,
    errors.Unauthenticated: HTTPStatus.UNAUTHORIZED,
    errors.Forbidden: HTTPStatus.FORBIDDEN,
    errors.NotFound: HTTPStatus.NOT_FOUND,
    errors.FeatureDisabled: HTTPStatus.NOT_FOUND,
    errors.Conflict: HTTPStatus.CONFLICT,
    errors.PreconditionFailed: HTTPStatus.PRECONDITION_FAILED,
    errors.UnsupportedMediaType: HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
}


def problem(
    status: HTTPStatus, slug: str, detail: str = "", field_errors: list[dict] | None = None
) -> JSONResponse:
    body: dict = {"type": f"urn:opengrc:problem:{slug}", "title": status.phrase, "status": status}
    if detail:
        body["detail"] = detail
    if field_errors:
        body["errors"] = field_errors
    headers = {"WWW-Authenticate": "Bearer"} if status == HTTPStatus.UNAUTHORIZED else None
    return JSONResponse(body, status, headers=headers, media_type="application/problem+json")


def _pointer(loc: tuple) -> str:
    # ("body", "name") -> "/name"; ("query", "limit") -> "/limit"
    return "/" + "/".join(str(part) for part in loc[1:]) if len(loc) > 1 else ""


def install(app: FastAPI) -> None:
    @app.exception_handler(errors.OpenGRCError)
    async def domain_error(_: Request, exc: errors.OpenGRCError) -> JSONResponse:
        status = STATUS.get(type(exc), HTTPStatus.INTERNAL_SERVER_ERROR)
        field_errors = (
            [{"detail": e.detail, "pointer": e.pointer} for e in exc.errors]
            if isinstance(exc, errors.Invalid)
            else None
        )
        return problem(status, exc.slug, exc.detail, field_errors)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def invalid(_: Request, exc: RequestValidationError | ValidationError) -> JSONResponse:
        field_errors = [{"detail": e["msg"], "pointer": _pointer(e["loc"])} for e in exc.errors()]
        return problem(HTTPStatus.BAD_REQUEST, "bad-request", field_errors=field_errors)
