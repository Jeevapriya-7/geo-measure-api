from fastapi import FastAPI

from app.routers_files import router as files_router

app = FastAPI(
    title="Geospatial File Measurement API",
    description="Upload a Shapefile (.zip) or KML and get area/length measurements per feature.",
    version="1.0.0",
)
app.include_router(files_router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
