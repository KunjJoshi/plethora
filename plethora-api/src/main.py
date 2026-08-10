from fastapi import FastAPI
from api.user import router as user_router
from api.agents import router as agents_router

app = FastAPI(title="Plethora API")

app.include_router(user_router)
app.include_router(agents_router)
