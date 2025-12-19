"""
PDF Portfolio Analysis Module

This module handles PDF portfolio statement analysis locally within the Host Agent.
It was previously a separate agent but has been integrated as a sub-agent for better performance.
"""

import boto3
import fitz  # PyMuPDF
import io
import os
import logging
from google import genai
from google.genai.types import GenerateContentConfig

# Import database functions at the top
try:
    from database import get_db, mark_portfolio_statement_uploaded
except ImportError:
    # Handle case where database module is in parent directory
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from database import get_db, mark_portfolio_statement_uploaded

logger = logging.getLogger("pdf_analyzer")


def read_portfolio_statement(session_id: str = "", user_name: str = "") -> str:
    """
    Reads portfolio statement PDF from S3 and returns text content.

    Args:
        session_id: The session ID for tracking (used for database updates and S3 filename)
        user_name: The user name (used for S3 filename)

    Returns:
        Extracted text from the PDF or error message
    """
    try:
        if not session_id or not user_name:
            return "Error: session_id and user_name are required to retrieve portfolio statement from S3"

        # Get S3 bucket name from environment
        bucket_name = os.getenv('S3_BUCKET_NAME', 'finance-a2a-portfolio-statements')

        # Construct S3 filename matching what was uploaded
        filename = f"{user_name}_{session_id}_portfolio_statement.pdf"

        logger.info(f"Attempting to download PDF from S3: s3://{bucket_name}/{filename}")

        # Initialize S3 client and download file
        s3_client = boto3.client('s3')

        # Download file to memory
        file_obj = io.BytesIO()
        s3_client.download_fileobj(bucket_name, filename, file_obj)
        file_obj.seek(0)
        file_bytes = file_obj.read()

        logger.info(f"Successfully downloaded {len(file_bytes)} bytes from S3")

    except s3_client.exceptions.NoSuchKey:
        return f"Error: Portfolio file not found in S3. Expected: s3://{bucket_name}/{filename}"
    except Exception as e:
        logger.error(f"Error downloading PDF from S3: {e}")
        return f"Error reading PDF file from S3: {e}"

    try:
        logger.info("Opening PDF with PyMuPDF...")
        pdf_document = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
        logger.info(f"PDF opened successfully. Number of pages: {len(pdf_document)}")

        text = ""
        for page_num in range(len(pdf_document)):
            logger.info(f"Processing page {page_num + 1}/{len(pdf_document)}")
            page = pdf_document.load_page(page_num)
            page_text = page.get_text()
            text += page_text
            logger.info(f"Page {page_num + 1} text length: {len(page_text)} characters")

        logger.info(f"Total text extracted: {len(text)} characters")

        # Mark portfolio statement as uploaded in the database if session_id is provided
        if session_id and text:
            try:
                db = next(get_db())
                success = mark_portfolio_statement_uploaded(db, session_id)
                if success:
                    logger.info(f"Successfully marked portfolio statement as uploaded for session {session_id}")
                else:
                    logger.info(f"Failed to mark portfolio statement as uploaded for session {session_id}")
            except Exception as e:
                logger.error(f"Error updating database for session {session_id}: {e}")

        return text

    except Exception as e:
        return f"Error processing PDF: {e}"


def extract_stock_tickers_from_portfolio(portfolio_text: str) -> str:
    """
    Extracts stock tickers from portfolio text using LLM.

    Args:
        portfolio_text: The portfolio statement text

    Returns:
        Formatted string with list of stock tickers found and their allocation percentages
    """
    try:
        logger.info(f"Starting LLM-based stock ticker extraction from {len(portfolio_text)} characters of text")

        # Create the client with proper configuration
        # Check if we should use Vertex AI or API key
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            client = genai.Client(vertexai=True)
            logger.info("Using Vertex AI for ticker extraction")
        else:
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.error("No GOOGLE_API_KEY found for ticker extraction")
                return "**Error**: Google API key not configured for ticker extraction. Please set GOOGLE_API_KEY environment variable."
            client = genai.Client(api_key=api_key)
            logger.info("Using Google AI API for ticker extraction")

        # System prompt for stock ticker extraction
        system_prompt = """You are an expert financial analyst specializing in analyzing portfolio statements and identifying stock ticker symbols.

Your task is to carefully analyze portfolio text and extract ALL stock ticker symbols mentioned.

Rules for extraction:
1. Extract only valid stock ticker symbols (typically 1-5 characters, letters only)
2. Look for company names and convert them to their ticker symbols (e.g., "Apple Inc." → "AAPL")
3. Include both individual stocks and ETFs
4. Convert all tickers to uppercase
5. Remove duplicates
6. Do NOT include common words, currency codes, or non-stock identifiers
7. Include tickers that appear in any context within the portfolio (holdings, transactions, etc.)
8. Calculate and include percentage allocation for each ticker based on portfolio value

Common patterns to look for:
- Direct ticker mentions: "AAPL", "GOOGL", "TSLA"
- Company names: "Apple Inc.", "Microsoft Corporation", "Tesla Inc."
- ETF names: "Vanguard S&P 500 ETF" → "VOO"
- Holdings tables with ticker columns
- Transaction records
- Position values and total portfolio value for percentage calculations

Respond with ONLY ticker symbols and their percentage allocations in this format:
AAPL (3.02%), GOOGL (9.66%), MSFT (3.95%), TSLA (0.61%), VOO (37.14%)

If no tickers are found, respond with: NONE"""

        # User prompt with the portfolio text
        user_prompt = f"""Analyze this portfolio statement text and extract ALL stock ticker symbols:

{portfolio_text}

Provide only the comma-separated ticker list as specified."""

        # Generate ticker extraction using LLM with retry logic
        logger.info("Generating ticker extraction using LLM...")
        max_retries = 3
        base_delay = 2.0
        response = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    import random
                    import time
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.info(f"Retrying ticker extraction after {delay:.2f}s delay (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=user_prompt,
                    config=GenerateContentConfig(
                        system_instruction=[system_prompt]
                    )
                )

                # If we get here, the call was successful
                logger.info(f"Successfully generated ticker extraction (attempt {attempt + 1})")
                break

            except Exception as e:
                error_message = str(e)
                is_api_error = any(code in error_message for code in ["500", "503", "INTERNAL", "UNAVAILABLE"])

                if attempt == max_retries - 1:
                    # Last attempt failed, re-raise the exception
                    logger.error(f"Failed to generate ticker extraction after {max_retries} attempts: {e}")
                    raise

                if is_api_error:
                    logger.warning(f"Google AI API error on attempt {attempt + 1}: {e}")
                else:
                    logger.warning(f"Non-API error on attempt {attempt + 1}: {e}")
                    # For non-API errors, fail immediately
                    raise

        found_tickers = []
        allocation_percentage = ""

        if response and response.text:
            # Parse the LLM response
            response_text = response.text.strip()
            logger.info(f"LLM ticker extraction response: {response_text}")

            # Store the raw LLM response for allocation percentage
            allocation_percentage = response_text

            # Parse the response
            if response_text.upper() != "NONE":
                # Split by commas and clean up
                ticker_list = response_text.split(',')
                for ticker_entry in ticker_list:
                    ticker_entry = ticker_entry.strip()
                    # Extract ticker symbol (before the parentheses if present)
                    if '(' in ticker_entry:
                        ticker = ticker_entry.split('(')[0].strip().upper()
                    else:
                        ticker = ticker_entry.strip().upper()
                    # Validate ticker format (1-5 characters, letters only)
                    if ticker and len(ticker) >= 1 and len(ticker) <= 5 and ticker.isalpha():
                        found_tickers.append(ticker)

                # Remove duplicates while preserving order
                found_tickers = list(dict.fromkeys(found_tickers))
        else:
            logger.error("No response from LLM for ticker extraction")
            return "**Error**: Could not extract tickers using LLM. Please try again."

        if not found_tickers:
            logger.info("No stock tickers found by LLM")
            return "No stock tickers found in the portfolio text. Please check if the portfolio statement contains stock symbols."

        logger.info(f"LLM found {len(found_tickers)} tickers: {found_tickers}")

        # Format the result
        result = f"**Stock Tickers Found in Portfolio:**\n\n"
        result += f"Total stocks identified: {len(found_tickers)}\n\n"
        result += "**Individual Stocks:**\n"
        for i, ticker in enumerate(found_tickers, 1):
            result += f"{i}. {ticker}\n"

        result += f"\n**Allocation Percentage:**\n"
        result += f"{allocation_percentage}\n"

        return result

    except Exception as e:
        logger.error(f"Error in extract_stock_tickers_from_portfolio: {e}")
        return f"Error extracting stock tickers: {e}"
