import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "message": "AI City Backend"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
