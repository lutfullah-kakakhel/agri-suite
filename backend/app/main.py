# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes_irrigation import router as irrigation_router

app = FastAPI(title="Irrigation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True, "service": "agri-suite-api"}

# IMPORTANT: include ONLY this router. No other include_router lines.
app.include_router(irrigation_router)
