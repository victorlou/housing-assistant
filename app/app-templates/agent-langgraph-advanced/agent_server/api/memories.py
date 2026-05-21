from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from agent_server.utils_memory import init_lakebase_config, lakebase_context

_config = init_lakebase_config()

memories_router = APIRouter()


def _namespace(user_id: str) -> tuple[str, str]:
    return ("user_memories", user_id.replace(".", "-"))


@memories_router.get("/user-memories")
async def list_memories(user_id: str = Query(...)):
    namespace = _namespace(user_id)
    async with lakebase_context(_config) as (_, store):
        results = await store.asearch(namespace, query=None, limit=50)
    return [
        {
            "key": item.key,
            "value": item.value,
            "updated_at": item.updated_at.isoformat() if getattr(item, "updated_at", None) else None,
        }
        for item in results
    ]


class MemoryBody(BaseModel):
    value: dict


@memories_router.put("/user-memories/{key}")
async def upsert_memory(key: str, body: MemoryBody, user_id: str = Query(...)):
    namespace = _namespace(user_id)
    async with lakebase_context(_config) as (_, store):
        await store.aput(namespace, key, body.value)
    return {"ok": True}


@memories_router.delete("/user-memories/{key}")
async def delete_memory(key: str, user_id: str = Query(...)):
    namespace = _namespace(user_id)
    async with lakebase_context(_config) as (_, store):
        await store.adelete(namespace, key)
    return {"ok": True}
