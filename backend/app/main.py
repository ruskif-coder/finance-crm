from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import auth, operations, reports, counterparties, articles, settings, users, roles

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Finance Management System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(operations.router, prefix="/api/operations", tags=["operations"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(counterparties.router, prefix="/api/counterparties", tags=["counterparties"])
app.include_router(articles.router, prefix="/api/articles", tags=["articles"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(roles.router, prefix="/api/roles", tags=["roles"])

@app.get("/")
def root():
    return {"status": "ok", "message": "Finance API running"}