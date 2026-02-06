"""
API Service for Layer 1: Deterministic Crawl Layer

This module provides a REST API for the web crawler service.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, Field

# Handle both relative and absolute imports
try:
    from .crawler import DeterministicCrawler, CrawlResult
except ImportError:
    # If running as script, add current directory to path
    sys.path.insert(0, str(Path(__file__).parent))
    from crawler import DeterministicCrawler, CrawlResult

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI-Powered Exploratory Testing Service",
    description="Layer 1: Deterministic Crawl Layer API",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for crawl results (in production, use a database)
crawl_results_storage: dict[str, list[CrawlResult]] = {}


class CrawlRequest(BaseModel):
    """Request model for crawl endpoint."""
    url: HttpUrl = Field(..., description="Starting URL for the crawl")
    max_pages: int = Field(50, ge=1, le=200, description="Maximum number of pages to crawl")
    max_depth: int = Field(5, ge=1, le=10, description="Maximum depth to crawl")
    same_domain_only: bool = Field(True, description="Only crawl pages from the same domain")
    headless: bool = Field(True, description="Run browser in headless mode")
    wait_time: float = Field(2.0, ge=0.5, le=10.0, description="Wait time after interactions (seconds)")


class CrawlResponse(BaseModel):
    """Response model for crawl endpoint."""
    crawl_id: str
    status: str
    message: str
    pages_crawled: int = 0


class CrawlStatusResponse(BaseModel):
    """Response model for crawl status endpoint."""
    crawl_id: str
    status: str
    pages_crawled: int
    total_pages: int
    results_available: bool


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AI-Powered Exploratory Testing Service",
        "layer": "Layer 1: Deterministic Crawl Layer",
        "version": "1.0.0",
        "endpoints": {
            "POST /api/v1/crawl": "Start a new crawl",
            "GET /api/v1/crawl/{crawl_id}/status": "Get crawl status",
            "GET /api/v1/crawl/{crawl_id}/results": "Get crawl results",
            "GET /api/v1/health": "Health check"
        }
    }


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "crawler"}


@app.post("/api/v1/crawl", response_model=CrawlResponse)
async def start_crawl(request: CrawlRequest, background_tasks: BackgroundTasks):
    """
    Start a new crawl job.
    
    This endpoint initiates a crawl and returns immediately with a crawl ID.
    The crawl runs in the background.
    """
    import uuid
    crawl_id = str(uuid.uuid4())
    
    logger.info(f"Starting crawl {crawl_id} for URL: {request.url}")
    
    # Initialize storage for this crawl
    crawl_results_storage[crawl_id] = []
    
    # Start crawl in background
    background_tasks.add_task(
        run_crawl,
        crawl_id=crawl_id,
        url=str(request.url),
        max_pages=request.max_pages,
        max_depth=request.max_depth,
        same_domain_only=request.same_domain_only,
        headless=request.headless,
        wait_time=request.wait_time
    )
    
    return CrawlResponse(
        crawl_id=crawl_id,
        status="started",
        message=f"Crawl started for {request.url}",
        pages_crawled=0
    )


@app.get("/api/v1/crawl/{crawl_id}/status", response_model=CrawlStatusResponse)
async def get_crawl_status(crawl_id: str):
    """Get the status of a crawl job."""
    if crawl_id not in crawl_results_storage:
        raise HTTPException(status_code=404, detail="Crawl ID not found")
    
    results = crawl_results_storage[crawl_id]
    
    # Check if crawl is complete (simple heuristic: if results exist, it's done)
    # In production, you'd track this more explicitly
    status = "completed" if results else "in_progress"
    
    return CrawlStatusResponse(
        crawl_id=crawl_id,
        status=status,
        pages_crawled=len(results),
        total_pages=len(results),
        results_available=len(results) > 0
    )


@app.get("/api/v1/crawl/{crawl_id}/results")
async def get_crawl_results(crawl_id: str, format: str = "json"):
    """
    Get crawl results.
    
    Args:
        crawl_id: The crawl ID
        format: Response format ('json' or 'raw')
    """
    if crawl_id not in crawl_results_storage:
        raise HTTPException(status_code=404, detail="Crawl ID not found")
    
    results = crawl_results_storage[crawl_id]
    
    if not results:
        raise HTTPException(status_code=202, detail="Crawl still in progress")
    
    crawler = DeterministicCrawler()
    crawler.crawl_results = results
    
    if format == "raw":
        return {"crawl_id": crawl_id, "results": results}
    else:
        return {
            "crawl_id": crawl_id,
            "pages_crawled": len(results),
            "results": crawler.get_results_json()
        }


def run_crawl(
    crawl_id: str,
    url: str,
    max_pages: int,
    max_depth: int,
    same_domain_only: bool,
    headless: bool,
    wait_time: float
):
    """Run the crawl and store results."""
    try:
        crawler = DeterministicCrawler(
            max_pages=max_pages,
            max_depth=max_depth,
            same_domain_only=same_domain_only,
            headless=headless,
            wait_time=wait_time
        )
        
        results = crawler.crawl(url)
        crawl_results_storage[crawl_id] = results
        
        logger.info(f"Crawl {crawl_id} completed. Visited {len(results)} pages.")
    
    except Exception as e:
        logger.error(f"Error in crawl {crawl_id}: {e}")
        # Store empty results on error
        crawl_results_storage[crawl_id] = []


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
