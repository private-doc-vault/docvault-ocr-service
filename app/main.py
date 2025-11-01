"""
DocVault OCR Service
FastAPI application for document OCR processing and metadata extraction
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os

from .routes import router
from .redis_queue import init_redis_queue_manager, get_redis_queue_manager

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="DocVault OCR Service",
    description="Document OCR processing and metadata extraction service",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    logger.info(f"Initializing Redis queue manager: {redis_url}")
    try:
        await init_redis_queue_manager(redis_url)
        logger.info("Redis queue manager initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Redis queue manager: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up services on shutdown"""
    logger.info("Shutting down services...")
    try:
        redis_manager = get_redis_queue_manager()
        await redis_manager.disconnect()
        logger.info("Redis queue manager disconnected successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "DocVault OCR Service", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "ocr"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)