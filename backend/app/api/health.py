from fastapi import APIRouter

router = APIRouter(tags=["health"])

# Served at the root, outside /api. It never touches the database, so the keep-awake ping
# every 50 s does not wake Neon (which would burn its free compute hours).
root_router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@root_router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
