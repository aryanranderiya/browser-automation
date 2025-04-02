from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.routes import router as routes_router
from utils.logger import setup_logger

# Set up application-wide logger
logger = setup_logger("crustdata_api")

app = FastAPI(title="CrustData Browser Automation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes_router)


@app.get("/")
async def read_root():
    logger.info("Root endpoint accessed")
    return {"message": "Welcome to CrustData Browser Automation API"}


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting CrustData Browser Automation API")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
