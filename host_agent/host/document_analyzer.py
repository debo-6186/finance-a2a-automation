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
import json
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

        # System prompt for stock ticker extraction with share quantities
        system_prompt = """You are an expert financial analyst specializing in analyzing portfolio data and extracting stock holdings information.

Your task is to carefully analyze portfolio text and extract ALL stock holdings with as much detail as possible.

EXTRACTION RULES:
1. Extract valid stock ticker symbols (1-5 characters, letters only)
2. Convert company names to ticker symbols (e.g., "Apple Inc." → "AAPL")
3. Include both individual stocks and ETFs
4. Convert all tickers to uppercase
5. Extract SHARE QUANTITIES when explicitly mentioned
6. Extract dollar amounts invested when mentioned
7. Extract percentage allocations when mentioned
8. Do NOT include common words, currency codes, or non-stock identifiers

PATTERNS TO LOOK FOR:
- Share quantities: "10.5 shares of AAPL", "GOOGL: 25 shares", "15.3 MSFT"
- Dollar amounts: "$3,500 in AAPL", "GOOGL - $8,200"
- Percentages: "10% AAPL", "AAPL (15.5%)"
- Combined: "AAPL: 10.5 shares, $3,500, 15%"
- Holdings tables with columns for ticker, shares, value, allocation
- Transaction records showing purchases

RESPONSE FORMAT - Return ONLY valid JSON in this EXACT format:
{
  "holdings": [
    {"ticker": "AAPL", "shares": 10.5, "allocation_pct": "3.02%", "amount": "$3500"},
    {"ticker": "GOOGL", "shares": 25.0, "allocation_pct": "9.66%", "amount": "$8200"}
  ]
}

FIELD REQUIREMENTS:
- ticker: Always required (string, uppercase)
- shares: Use actual number if mentioned, otherwise 0 (number)
- allocation_pct: Include if mentioned, otherwise null (string or null)
- amount: Include if mentioned, otherwise null (string or null)

If no tickers are found, respond with: {"holdings": []}

IMPORTANT: Extract EXACT share numbers when visible in the portfolio. Do not estimate or calculate."""

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

        holdings_data = []

        if response and response.text:
            # Parse the LLM response
            response_text = response.text.strip()
            logger.info(f"LLM holdings extraction response: {response_text[:500]}...")

            try:
                # Clean JSON response (remove markdown code blocks if present)
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                    response_text = response_text.strip()

                # Parse JSON
                holdings_json = json.loads(response_text)
                holdings_data = holdings_json.get("holdings", [])

                logger.info(f"Successfully parsed {len(holdings_data)} holdings")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Response text: {response_text}")
                return f"**Error**: Could not parse holdings data. Please try again."

        else:
            logger.error("No response from LLM for holdings extraction")
            return "**Error**: Could not extract holdings using LLM. Please try again."

        if not holdings_data:
            logger.info("No stock holdings found by LLM")
            return "No stock holdings found in the portfolio data. Please check if the input contains stock information."

        logger.info(f"LLM found {len(holdings_data)} holdings")

        # Format the result with detailed holdings information
        result = f"**Portfolio Holdings Extracted:**\n\n"
        result += f"Total stocks identified: {len(holdings_data)}\n\n"

        # Separate holdings into those with shares and those without
        with_shares = [h for h in holdings_data if h.get('shares', 0) > 0]
        without_shares = [h for h in holdings_data if h.get('shares', 0) == 0]

        if with_shares:
            result += "**Holdings with Share Quantities:**\n"
            for holding in with_shares:
                ticker = holding.get('ticker', 'N/A')
                shares = holding.get('shares', 0)
                allocation = holding.get('allocation_pct', 'N/A')
                amount = holding.get('amount', 'N/A')
                result += f"• {ticker}: {shares} shares"
                if allocation != 'N/A' and allocation:
                    result += f" ({allocation})"
                if amount != 'N/A' and amount:
                    result += f" - {amount}"
                result += "\n"
            result += "\n"

        if without_shares:
            result += "**Holdings Missing Share Counts (will ask user):**\n"
            for holding in without_shares:
                ticker = holding.get('ticker', 'N/A')
                allocation = holding.get('allocation_pct', 'N/A')
                amount = holding.get('amount', 'N/A')
                result += f"• {ticker}"
                if allocation != 'N/A' and allocation:
                    result += f" ({allocation})"
                if amount != 'N/A' and amount:
                    result += f" - {amount}"
                result += "\n"

        # Store holdings data as JSON string for later use
        result += f"\n**HOLDINGS_DATA_JSON:**\n{json.dumps(holdings_data)}\n"

        return result

    except Exception as e:
        logger.error(f"Error in extract_stock_tickers_from_text: {e}")
        return f"Error extracting stock tickers: {e}"
