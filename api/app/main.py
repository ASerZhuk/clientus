from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import get_settings
from .services.subscription import SubscriptionError

from .routers import admin, internal, leads, owner, public

app = FastAPI(title="Clientus API", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
app.include_router(public.router)
app.include_router(leads.router)
app.include_router(owner.router)
if get_settings().admin_enabled:  # a customer's own server has no operator panel
    app.include_router(admin.router)
app.include_router(internal.router)


@app.exception_handler(SubscriptionError)
async def subscription_error(_request: Request, exc: SubscriptionError):
    return JSONResponse({"detail": {"code": exc.code, **exc.detail}}, status_code=402)


@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if "/owner" in path or "/my/" in path or path.endswith("/my/booking") or path.startswith(("/api/admin", "/api/internal")):
        response.headers["Cache-Control"] = "no-store"  # never stored by browsers, proxies or the service worker
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response
