import json
import os
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from logger import setup_logging, get_logger

# Configure logging
setup_logging()
logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Stock Ticker API",
    description="API for managing stock tickers by type",
    version="1.0.0"
)

# Data model for the request
class StockTickerRequest(BaseModel):
    stock_type: str
    stock_tickers: List[str]

# Data model for the response
class StockTickerResponse(BaseModel):
    message: str
    stock_type: str
    stock_tickers: List[str]

# File path for storing the JSON data
STOCK_DATA_FILE = "stock_data.json"

def load_stock_data() -> dict:
    """Load existing stock data from JSON file."""
    if os.path.exists(STOCK_DATA_FILE):
        try:
            with open(STOCK_DATA_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading stock data: {e}")
            return {}
    return {}

def save_stock_data(data: dict) -> None:
    """Save stock data to JSON file."""
    try:
        with open(STOCK_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Stock data saved successfully")
    except IOError as e:
        logger.error(f"Error saving stock data: {e}")
        raise HTTPException(status_code=500, detail="Failed to save stock data")

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Stock Ticker API is running"}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

@app.post("/stock-tickers", response_model=StockTickerResponse)
async def upsert_stock_tickers(request: StockTickerRequest):
    """
    Upsert stock tickers for a given stock type.
    
    Args:
        request: StockTickerRequest containing stock_type and stock_tickers
        
    Returns:
        StockTickerResponse with confirmation message and updated data
    """
    try:
        # Load existing data
        stock_data = load_stock_data()
        
        # Upsert the stock tickers for the given type
        stock_data[request.stock_type] = request.stock_tickers
        
        # Save the updated data
        save_stock_data(stock_data)
        
        logger.info(f"Successfully upserted {len(request.stock_tickers)} tickers for type '{request.stock_type}'")
        
        return StockTickerResponse(
            message=f"Successfully upserted {len(request.stock_tickers)} stock tickers for type '{request.stock_type}'",
            stock_type=request.stock_type,
            stock_tickers=request.stock_tickers
        )
        
    except Exception as e:
        logger.error(f"Error upserting stock tickers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upsert stock tickers: {str(e)}")