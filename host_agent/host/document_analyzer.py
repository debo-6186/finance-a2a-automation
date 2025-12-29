"""
Multi-Format Portfolio Document Analyzer

This module handles portfolio data extraction from multiple formats:
- PDF documents
- Image files (JPG, PNG, etc.)
- Plain text input
"""

import boto3
import fitz  # PyMuPDF
import io
import os
import logging
from typing import Tuple
from google import genai
from google.genai.types import GenerateContentConfig, Part
from PIL import Image

# Import database functions and config at the top
try:
    from database import get_db, mark_portfolio_statement_uploaded
    from config import current_config
except ImportError:
    # Handle case where database module is in parent directory
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from database import get_db, mark_portfolio_statement_uploaded
    from config import current_config

# Configure logger - will use parent logger's handlers (host_agent_api)
logger = logging.getLogger("host_agent_api.document_analyzer")
logger.setLevel(logging.INFO)


def detect_file_format(filename: str) -> str:
    """
    Detect the format of the uploaded file based on extension.

    Args:
        filename: Name of the uploaded file

    Returns:
        Format type: 'pdf', 'image', or 'unknown'
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext == '.pdf':
        return 'pdf'
    elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
        return 'image'
    else:
        return 'unknown'


def read_pdf_document(file_bytes: bytes) -> str:
    """
    Extract text from PDF document.

    Args:
        file_bytes: PDF file content as bytes

    Returns:
        Extracted text from the PDF
    """
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
        return text

    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        return f"Error processing PDF: {e}"


def read_image_document(file_bytes: bytes) -> str:
    """
    Extract text from image document using Google Gemini Vision.

    Args:
        file_bytes: Image file content as bytes

    Returns:
        Extracted text from the image
    """
    try:
        logger.info(f"Processing image document ({len(file_bytes)} bytes)")

        # Verify image can be opened
        image = Image.open(io.BytesIO(file_bytes))
        logger.info(f"Image format: {image.format}, Size: {image.size}")

        # Use Google Gemini Vision to extract text
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            client = genai.Client(vertexai=True)
            logger.info("Using Vertex AI for image text extraction")
        else:
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.error("No GOOGLE_API_KEY found for image text extraction")
                return "**Error**: Google API key not configured for image extraction. Please set GOOGLE_API_KEY environment variable."
            client = genai.Client(api_key=api_key)
            logger.info("Using Google AI API for image text extraction")

        # System prompt for extracting portfolio data from image
        system_prompt = """You are an expert financial analyst analyzing portfolio screenshots or images.

Your task is to extract ALL text and data from the portfolio image, paying special attention to:
1. Stock ticker symbols
2. Company names
3. Share quantities
4. Position values
5. Percentage allocations
6. Total portfolio value
7. Any other relevant financial information

Extract and format the information in a clear, structured way that preserves all the original data."""

        # Create image part for Gemini
        image_part = Part.from_bytes(
            data=file_bytes,
            mime_type=f"image/{image.format.lower()}" if image.format else "image/jpeg"
        )

        # Generate text extraction using Vision LLM
        logger.info("Generating text extraction from image using Vision LLM...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image_part, "Extract all portfolio data from this image."],
            config=GenerateContentConfig(
                system_instruction=[system_prompt]
            )
        )

        if response and response.text:
            extracted_text = response.text.strip()
            logger.info(f"Successfully extracted {len(extracted_text)} characters from image")
            return extracted_text
        else:
            logger.error("No response from Vision LLM")
            return "Error: Could not extract text from image"

    except Exception as e:
        logger.error(f"Error processing image: {e}")
        return f"Error processing image: {e}"


def read_portfolio_document(session_id: str = "", user_name: str = "", input_format: str = "") -> Tuple[str, str]:
    """
    Reads portfolio document from local storage or S3 and returns text content.
    Supports PDF and image formats.

    Args:
        session_id: The session ID for tracking
        user_name: The user name
        input_format: The format type ('pdf' or 'image')

    Returns:
        Tuple of (extracted_text, actual_format)
    """
    try:
        if not session_id or not user_name:
            return "Error: session_id and user_name are required to retrieve portfolio document", ""

        # Determine file extension based on format
        if input_format == 'pdf':
            file_ext = '.pdf'
        elif input_format == 'image':
            # We'll need to check multiple image extensions
            file_ext = None
        else:
            return f"Error: Unsupported input format '{input_format}'", ""

        # Construct base filename
        base_filename = f"{user_name}_{session_id}_portfolio_statement"

        logger.info(f"Attempting to read document: {base_filename} (format: {input_format})")
        logger.info(f"Environment: {current_config.ENVIRONMENT}")

        # Get file bytes from storage
        file_bytes = None
        actual_format = input_format

        # Check if local or production environment
        if current_config.is_local():
            # LOCAL STORAGE
            storage_path = current_config.LOCAL_STORAGE_PATH

            if file_ext:
                # Specific extension
                file_path = os.path.join(storage_path, base_filename + file_ext)
                logger.info(f"Reading from local storage: {file_path}")

                if not os.path.exists(file_path):
                    return f"Error: Portfolio file not found in local storage. Expected: {file_path}", ""

                with open(file_path, 'rb') as f:
                    file_bytes = f.read()
            else:
                # Try different image extensions
                image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
                for ext in image_extensions:
                    file_path = os.path.join(storage_path, base_filename + ext)
                    if os.path.exists(file_path):
                        logger.info(f"Found image file: {file_path}")
                        with open(file_path, 'rb') as f:
                            file_bytes = f.read()
                        break

                if not file_bytes:
                    return f"Error: No portfolio image found in local storage with common extensions", ""

            logger.info(f"Successfully read {len(file_bytes)} bytes from local storage")

        else:
            # S3 STORAGE (Production)
            bucket_name = current_config.S3_BUCKET_NAME
            s3_client = boto3.client('s3')

            if file_ext:
                # Specific extension
                filename = base_filename + file_ext
                logger.info(f"Attempting to download from S3: s3://{bucket_name}/{filename}")

                file_obj = io.BytesIO()
                try:
                    s3_client.download_fileobj(bucket_name, filename, file_obj)
                    file_obj.seek(0)
                    file_bytes = file_obj.read()
                    logger.info(f"Successfully downloaded {len(file_bytes)} bytes from S3")
                except s3_client.exceptions.NoSuchKey:
                    return f"Error: Portfolio file not found in S3. Expected: s3://{bucket_name}/{filename}", ""
            else:
                # Try different image extensions
                image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
                for ext in image_extensions:
                    filename = base_filename + ext
                    file_obj = io.BytesIO()
                    try:
                        s3_client.download_fileobj(bucket_name, filename, file_obj)
                        file_obj.seek(0)
                        file_bytes = file_obj.read()
                        logger.info(f"Successfully downloaded {len(file_bytes)} bytes from S3: {filename}")
                        break
                    except Exception as e:
                        # Catch any exception (404, NoSuchKey, etc.) and continue
                        logger.debug(f"File not found with extension {ext}: {e}")
                        continue

                if not file_bytes:
                    return f"Error: No portfolio image found in S3 with common extensions", ""

    except Exception as e:
        logger.error(f"Error reading portfolio file: {e}")
        return f"Error reading document: {e}", ""

    # Extract text based on format
    try:
        if actual_format == 'pdf':
            text = read_pdf_document(file_bytes)
        elif actual_format == 'image':
            text = read_image_document(file_bytes)
        else:
            return f"Error: Unsupported format '{actual_format}'", ""

        # Mark portfolio statement as uploaded in the database if session_id is provided
        if session_id and text and not text.startswith("Error"):
            try:
                db = next(get_db())
                success = mark_portfolio_statement_uploaded(db, session_id, input_format=actual_format)
                if success:
                    logger.info(f"Successfully marked portfolio statement as uploaded ({actual_format}) for session {session_id}")
                else:
                    logger.info(f"Failed to mark portfolio statement as uploaded for session {session_id}")
            except Exception as e:
                logger.error(f"Error updating database for session {session_id}: {e}")

        return text, actual_format

    except Exception as e:
        logger.error(f"Error extracting text from document: {e}")
        return f"Error extracting text: {e}", ""


def extract_stock_tickers_from_text(portfolio_text: str) -> str:
    """
    Extracts stock tickers from portfolio text using LLM.
    Works with text from PDFs, images, or direct text input.

    Args:
        portfolio_text: The portfolio text (from any source)

    Returns:
        Formatted string with list of stock tickers found and their allocation percentages
    """
    try:
        logger.info(f"Starting LLM-based stock ticker extraction from {len(portfolio_text)} characters of text")

        # Create the client with proper configuration
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
        system_prompt = """You are an expert financial analyst specializing in analyzing portfolio data and identifying stock ticker symbols.

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
- Text like "10% AAPL, 20% GOOGL" or "AAPL 10%, GOOGL 20%"
- Simple lists like "AAPL, GOOGL, MSFT"

Respond with ONLY ticker symbols and their percentage allocations in this format:
AAPL (3.02%), GOOGL (9.66%), MSFT (3.95%), TSLA (0.61%), VOO (37.14%)

If percentages are not available, estimate based on context or use equal distribution.
If no tickers are found, respond with: NONE"""

        # User prompt with the portfolio text
        user_prompt = f"""Analyze this portfolio data and extract ALL stock ticker symbols:

{portfolio_text}

Provide only the comma-separated ticker list with percentages as specified."""

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
            return "No stock tickers found in the portfolio data. Please check if the input contains stock symbols."

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
        logger.error(f"Error in extract_stock_tickers_from_text: {e}")
        return f"Error extracting stock tickers: {e}"
