from contextlib import asynccontextmanager

from anthropic import AsyncAnthropic
from fastapi import FastAPI, HTTPException, Request

from virtualme import __version__
from virtualme.config import Settings, sqlite_path
from virtualme.interview.question_selector import QuestionSelector, load_question_pool
from virtualme.storage.db import DB
from virtualme.transport.line import handle_line_webhook

settings = Settings()
db = DB(sqlite_path(settings.database_url))
claude = AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value(), max_retries=4)
selector = QuestionSelector(load_question_pool())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.init()
    yield


app = FastAPI(title="VirtualMe", version=__version__, lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"ok": "true", "version": __version__}


@app.post("/webhook/line")
async def line_webhook(request: Request) -> dict:
    secret = (
        settings.line_channel_secret.get_secret_value()
        if settings.line_channel_secret is not None
        else None
    )
    result = await handle_line_webhook(request, claude, db, selector, secret, settings)
    if result.get("status") == "invalid_signature":
        raise HTTPException(status_code=400, detail="invalid LINE signature")
    if result.get("status") == "missing_line_credentials":
        raise HTTPException(status_code=503, detail="LINE credentials are not configured")
    return result
