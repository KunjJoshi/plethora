from fastapi import FastAPI
from api.user import router as user_router
from api.agents import router as agents_router
from api.third_party import router as third_party_router
from api.subscriptions import router as subscriptions_router
from api.tasks import router as tasks_router

app = FastAPI(title="Plethora API")

app.include_router(user_router)
app.include_router(agents_router)
app.include_router(third_party_router)
app.include_router(subscriptions_router)
app.include_router(tasks_router)
