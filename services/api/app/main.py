from fastapi import FastAPI

app = FastAPI(title="Super Agent API")


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
