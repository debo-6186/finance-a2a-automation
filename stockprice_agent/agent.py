import yfinance as yf
from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)

class StockPriceAgent:
    """Agent for fetching real-time US stock prices by ticker symbol."""

    async def get_stock_price(self, ticker: str) -> Dict[str, Any]:
        if not ticker or not isinstance(ticker, str):
            return {
                "is_task_complete": True,
                "require_user_input": True,
                "content": "No ticker symbol provided. Please provide a valid US stock ticker (e.g., AAPL, TSLA).",
            }
        try:
            ticker = ticker.strip().upper()
            logger.info(f"Attempting to fetch price for ticker: {ticker}")
            stock_info = yf.Ticker(ticker).info
            logger.info(f"Stock info: {stock_info}")
            price = stock_info.get("regularMarketPrice")
            logger.info(f"Fetched price for {ticker}: {price}")
            if price is not None:
                return {
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": f"The current price of {ticker} is ${price} (USD).",
                }
            else:
                return {
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": f"Could not fetch price for ticker '{ticker}'. Please check if the symbol is correct and try again.",
                }
        except Exception as e:
            logger.error(f"Error fetching price for {ticker}: {e}")
            return {
                "is_task_complete": True,
                "require_user_input": False,
                "content": f"An error occurred while fetching the stock price: {str(e)}",
            }
