from dataclasses import dataclass
from typing import Callable
from fastapi import Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Query as SAQuery
from redis_cache import get_cache, set_cache

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


@dataclass
class Page:
    limit: int
    offset: int


def page_params(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> Page:
    return Page(limit=limit, offset=offset)


def paginate(
    query: SAQuery,
    page: Page,
    response: Response,
    build: Callable,
    schema: type[BaseModel],
    cache_key: str | None = None,
) -> list:
    """Return one page as a plain list and set X-Total-Count. With cache_key, cache each page separately."""
    key = f"{cache_key}:limit:{page.limit}:offset:{page.offset}" if cache_key else None
    cached = get_cache(key) if key else None
    if cached:
        response.headers["X-Total-Count"] = str(cached["total"])
        return [schema(**item) for item in cached["items"]]

    total = query.order_by(None).count()
    items = [build(row) for row in query.offset(page.offset).limit(page.limit).all()]
    if key:
        set_cache(key, {"total": total, "items": [item.model_dump(mode="json") for item in items]})
    response.headers["X-Total-Count"] = str(total)
    return items
