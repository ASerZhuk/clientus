"""Landing page requests ("connect online booking"). Public, rate-limited; the operator reads them in /admin."""
from fastapi import APIRouter, Request

from .. import db as database
from ..models import Lead
from ..ratelimit import limit_request
from ..schemas import LeadIn

router = APIRouter(prefix="/api")


@router.post("/leads", status_code=201)
def create_lead(body: LeadIn, request: Request) -> dict:
    limit_request(request, 0, "lead", 5, 3600, per_tenant=200)
    if body.website:  # a bot filled the hidden field: pretend success, store nothing
        return {"ok": True}
    with database.write_session() as db:
        db.add(Lead(name=body.name, phone=body.phone, business=body.business, kind=body.kind, city=body.city, comment=body.comment))
    return {"ok": True}
