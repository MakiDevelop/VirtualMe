from pathlib import Path

from anthropic import AsyncAnthropic
from fastapi import FastAPI, Request

from virtualme import __version__
from virtualme.config import Settings, sqlite_path
from virtualme.interview.question_selector import QuestionSelector, load_question_pool
from virtualme.storage.db import DB
from virtualme.transport.line import handle_line_webhook

settings = Settings()
db = DB(sqlite_path(settings.database_url))
claude = AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
question_pool_path = Path("specs/question-pool.yaml")
selector = QuestionSelector(load_question_pool(question_pool_path) if question_pool_path.exists() else {})
app = FastAPI(title="VirtualMe", version=__version__)


@app.on_event("startup")
async def startup() -> None:
    await db.init()


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
    return await handle_line_webhook(request, claude, db, selector, secret, settings)
