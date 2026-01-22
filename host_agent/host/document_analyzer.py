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


def verify_portfolio_document(file_bytes: bytes, file_format: str) -> Tuple[bool, str]:
    """
    Verify if the uploaded document is actually a portfolio statement or report.
    Uses Gemini 2.5 Flash to analyze the content and determine validity.

    Args:
        file_bytes: The file content as bytes
        file_format: The format type ('pdf' or 'image')

    Returns:
        Tuple of (is_valid, message)
        - is_valid: True if document is a valid portfolio statement, False otherwise
        - message: Explanation message
    """
    try:
        logger.info(f"Verifying {file_format} document ({len(file_bytes)} bytes)")

        # Create the client with proper configuration
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            client = genai.Client(vertexai=True)
            logger.info("Using Vertex AI for document verification")
        else:
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.error("No GOOGLE_API_KEY found for document verification")
                return False, "**Error**: Google API key not configured. Please set GOOGLE_API_KEY environment variable."
            client = genai.Client(api_key=api_key)
            logger.info("Using Google AI API for document verification")

        # System prompt for document verification
        system_prompt = """You are an expert financial document analyst specializing in portfolio statements and investment reports.

Your task is to verify if a document is a VALID PORTFOLIO STATEMENT or INVESTMENT REPORT.

VALID PORTFOLIO DOCUMENTS contain at least ONE of the following:
1. Stock holdings (ticker symbols, company names, shares, values)
2. Investment positions (mutual funds, ETFs, bonds)
3. Portfolio summary (total value, asset allocation)
4. Brokerage account statements (trades, positions, balances)
5. Investment account screenshots (from apps like Robinhood, E*TRADE, Zerodha, etc.)
6. Holdings tables or lists with financial data
7. Transaction history with stock purchases/sales

INVALID DOCUMENTS (reject these):
- Bank statements without investment holdings
- Credit card statements
- Utility bills
- Personal documents (ID, passport, etc.)
- Random screenshots without portfolio data
- News articles or research reports
- Empty or corrupted files
- General financial documents without specific holdings

RESPONSE FORMAT - Return ONLY valid JSON in this EXACT format:
{
  "is_valid": true/false,
  "confidence": "high/medium/low",
  "document_type": "portfolio statement/brokerage account/investment report/not portfolio related",
  "reason": "Brief explanation of your decision"
}

Be strict but fair - if you're unsure but see ANY investment holdings, mark as valid with low confidence."""

        # Process based on file format
        if file_format == 'pdf':
            # Extract text from PDF
            text = read_pdf_document(file_bytes)
            if text.startswith("Error"):
                return False, f"Could not verify document: {text}"

            user_prompt = f"""Analyze this document text and determine if it's a valid portfolio statement:

{text[:4000]}

Provide your verification response in the specified JSON format."""

            logger.info("Verifying PDF document with LLM...")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=GenerateContentConfig(
                    system_instruction=[system_prompt]
                )
            )

        elif file_format == 'image':
            # Verify image can be opened
            image = Image.open(io.BytesIO(file_bytes))
            logger.info(f"Verifying image: {image.format}, Size: {image.size}")

            # Create image part for Gemini Vision
            image_part = Part.from_bytes(
                data=file_bytes,
                mime_type=f"image/{image.format.lower()}" if image.format else "image/jpeg"
            )

            user_prompt = "Analyze this image and determine if it's a valid portfolio statement or investment report. Provide your verification response in the specified JSON format."

            logger.info("Verifying image document with Vision LLM...")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[image_part, user_prompt],
                config=GenerateContentConfig(
                    system_instruction=[system_prompt]
                )
            )
        else:
            return False, f"Unsupported file format: {file_format}"

        # Parse the LLM response
        if response and response.text:
            response_text = response.text.strip()
            logger.info(f"Verification response: {response_text}")

            try:
                # Clean JSON response (remove markdown code blocks if present)
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                    response_text = response_text.strip()

                # Parse JSON
                verification_result = json.loads(response_text)
                is_valid = verification_result.get("is_valid", False)
                confidence = verification_result.get("confidence", "low")
                document_type = verification_result.get("document_type", "unknown")
                reason = verification_result.get("reason", "No reason provided")

                logger.info(f"Verification result: valid={is_valid}, confidence={confidence}, type={document_type}")

                if is_valid:
                    message = f"Document verified as valid {document_type} (confidence: {confidence}). {reason}"
                    return True, message
                else:
                    message = f"**Invalid Document**: This does not appear to be a portfolio statement or investment report.\n\n"
                    message += f"Document type detected: {document_type}\n"
                    message += f"Reason: {reason}\n\n"
                    message += "**Please upload a valid portfolio statement** (brokerage account statement, investment app screenshot, or holdings report) "
                    message += "**OR enter your portfolio details as text** (e.g., 'AAPL 30%, GOOGL 20%, MSFT 15%')."
                    return False, message

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse verification JSON: {e}")
                logger.error(f"Response text: {response_text}")
                # If we can't parse, assume invalid for safety
                return False, "Could not verify document format. Please ensure you're uploading a portfolio statement or enter your holdings as text."
        else:
            logger.error("No response from LLM for document verification")
            return False, "Could not verify document. Please try again or enter your portfolio as text."

    except Exception as e:
        logger.error(f"Error verifying portfolio document: {e}")
        return False, f"Error during verification: {str(e)}. Please try uploading again or enter your portfolio as text."


def verify_text_portfolio(text_input: str) -> Tuple[bool, str]:
    """
    Verify if the text input contains valid portfolio information.
    Uses Gemini 2.5 Flash to analyze the text content.

    Args:
        text_input: The user's text input

    Returns:
        Tuple of (is_valid, message)
        - is_valid: True if text contains valid portfolio data, False otherwise
        - message: Explanation message
    """
    try:
        logger.info(f"Verifying text portfolio input ({len(text_input)} characters)")

        # Quick validation - if text is too short, likely not portfolio data
        if len(text_input.strip()) < 10:
            return False, "**Invalid Input**: Please provide portfolio information with stock tickers or company names."

        # Create the client with proper configuration
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            client = genai.Client(vertexai=True)
            logger.info("Using Vertex AI for text verification")
        else:
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.error("No GOOGLE_API_KEY found for text verification")
                return False, "**Error**: Google API key not configured."
            client = genai.Client(api_key=api_key)
            logger.info("Using Google AI API for text verification")

        # System prompt for text verification
        system_prompt = """You are an expert financial analyst specializing in portfolio data analysis.

Your task is to verify if user text input contains VALID PORTFOLIO INFORMATION.

VALID PORTFOLIO TEXT contains at least ONE of the following:
1. Stock ticker symbols (AAPL, GOOGL, MSFT, etc.)
2. Company names with investment context (Apple Inc., Google, Microsoft)
3. Holdings with percentages (AAPL 30%, GOOGL 20%)
4. Share quantities (10 shares of AAPL, GOOGL 25 shares)
5. Investment amounts ($5000 in AAPL, GOOGL - $3000)
6. Portfolio descriptions or lists

INVALID TEXT (reject these):
- Random words or gibberish
- Questions without portfolio data ("What should I invest in?")
- General financial discussions without specific holdings
- Empty or very short text
- Non-portfolio related content

RESPONSE FORMAT - Return ONLY valid JSON in this EXACT format:
{
  "is_valid": true/false,
  "confidence": "high/medium/low",
  "reason": "Brief explanation of your decision"
}

Be lenient - if you see ANY stock tickers or company names in investment context, mark as valid."""

        user_prompt = f"""Analyze this user text and determine if it contains valid portfolio information:

"{text_input}"

Provide your verification response in the specified JSON format."""

        logger.info("Verifying text input with LLM...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=GenerateContentConfig(
                system_instruction=[system_prompt]
            )
        )

        # Parse the LLM response
        if response and response.text:
            response_text = response.text.strip()
            logger.info(f"Text verification response: {response_text}")

            try:
                # Clean JSON response (remove markdown code blocks if present)
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                    response_text = response_text.strip()

                # Parse JSON
                verification_result = json.loads(response_text)
                is_valid = verification_result.get("is_valid", False)
                confidence = verification_result.get("confidence", "low")
                reason = verification_result.get("reason", "No reason provided")

                logger.info(f"Text verification result: valid={is_valid}, confidence={confidence}")

                if is_valid:
                    message = f"Portfolio text verified (confidence: {confidence}). {reason}"
                    return True, message
                else:
                    message = f"**Invalid Portfolio Input**: The text provided does not contain recognizable portfolio information.\n\n"
                    message += f"Reason: {reason}\n\n"
                    message += "**Please provide portfolio details** in one of these formats:\n"
                    message += "- Stock tickers with percentages: 'AAPL 30%, GOOGL 20%, MSFT 15%'\n"
                    message += "- Holdings with shares: 'AAPL 10 shares, GOOGL 25 shares'\n"
                    message += "- Company names: 'Apple Inc., Google, Microsoft'\n"
                    message += "**OR upload a portfolio statement file** (PDF or image)."
                    return False, message

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse text verification JSON: {e}")
                logger.error(f"Response text: {response_text}")
                # If we can't parse, be lenient and allow it through
                return True, "Could not fully verify text format, proceeding with analysis."
        else:
            logger.error("No response from LLM for text verification")
            # If no response, be lenient and allow it through
            return True, "Could not verify text format, proceeding with analysis."

    except Exception as e:
        logger.error(f"Error verifying text portfolio: {e}")
        # On error, be lenient and allow it through
        return True, f"Verification error, proceeding with analysis: {str(e)}"


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


def validate_exchange_consistency(holdings_data: list, user_market_preference: str = None) -> Tuple[bool, str, str]:
    """
    Validates that all assets (stocks and ETFs) belong to the same country and rejects crypto/unsupported assets.
    Allows ETFs and index funds from the same country as stocks (e.g., US stocks + US ETFs is valid).
    Also validates against user's market preference if provided.

    Args:
        holdings_data: List of holdings dictionaries with ticker symbols
        user_market_preference: User's chosen market preference ("US" or "INDIA"), if set

    Returns:
        Tuple of (is_valid, message, primary_exchange)
        - is_valid: True if all assets are from same country and no crypto/unsupported assets, False otherwise
        - message: Explanation message
        - primary_exchange: The primary country/exchange ("US", "India", "Mixed", or "Unknown")
    """
    try:
        if not holdings_data:
            return True, "No holdings to validate", "Unknown"

        logger.info(f"Validating exchange consistency for {len(holdings_data)} holdings")

        # Create the client with proper configuration
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            client = genai.Client(vertexai=True)
            logger.info("Using Vertex AI for exchange validation")
        else:
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.error("No GOOGLE_API_KEY found for exchange validation")
                return False, "**Error**: Google API key not configured for validation.", "Unknown"
            client = genai.Client(api_key=api_key)
            logger.info("Using Google AI API for exchange validation")

        # Extract just the tickers for validation
        tickers = [holding.get('ticker', '') for holding in holdings_data if holding.get('ticker')]
        tickers_str = ", ".join(tickers)

        # System prompt for exchange validation
        system_prompt = """You are an expert financial analyst specializing in stock exchange classification.

Your task is to analyze a list of stock tickers and determine:
1. Which stock exchange/country each ticker belongs to (US or India)
2. Whether any tickers are cryptocurrencies or other unsupported assets
3. Whether all assets belong to the SAME country/exchange

EXCHANGE IDENTIFICATION RULES:
- **US Assets**: Ticker symbols without country suffixes (e.g., AAPL, GOOGL, MSFT, TSLA, AMZN, VOO, SPY, QQQ)
  - Includes individual stocks AND ETFs/index funds
  - Usually 1-5 uppercase letters
  - Listed on NYSE, NASDAQ, etc.
  - Examples: AAPL (stock), VOO (ETF), SPY (ETF), QQQ (ETF)

- **Indian Assets**: Ticker symbols with .NS (NSE) or .BO (BSE) suffixes (e.g., RELIANCE.NS, TCS.BO, INFY.NS)
  - Includes individual stocks AND ETFs/index funds from India
  - May also be Indian company names without suffixes that are clearly Indian companies
  - Listed on NSE (National Stock Exchange) or BSE (Bombay Stock Exchange)
  - Examples: RELIANCE.NS (stock), NIFTYBEES.NS (ETF)

- **Cryptocurrencies**: BTC, ETH, DOGE, BNB, ADA, SOL, XRP, USDT, USDC, etc.
  - These are NOT supported and must be REJECTED

- **Other Assets**: Commodities, forex, bonds, etc.
  - These are NOT supported and must be REJECTED

VALIDATION RULES:
1. ETFs and index funds are ALLOWED from the same country as stocks (e.g., US stock + US ETF = valid)
2. ALL assets must belong to the SAME country/exchange (all US OR all India)
3. Mixing assets from DIFFERENT countries is INVALID (e.g., US stock + Indian stock = invalid)
4. Cryptocurrencies and unsupported assets must be REJECTED

RESPONSE FORMAT - Return ONLY valid JSON in this EXACT format:
{
  "is_valid": true/false,
  "primary_exchange": "US" or "India" or "Mixed" or "Unknown",
  "invalid_assets": [
    {"ticker": "BTC", "type": "cryptocurrency", "reason": "Cryptocurrencies not supported"},
    {"ticker": "GOLD", "type": "commodity", "reason": "Commodities not supported"}
  ],
  "exchange_breakdown": {
    "us_assets": ["AAPL", "VOO", "GOOGL"],
    "india_assets": ["RELIANCE.NS", "TCS.BO", "NIFTYBEES.NS"],
    "crypto": ["BTC", "ETH"],
    "other": ["GOLD"]
  },
  "message": "Detailed explanation of the validation result"
}

IMPORTANT NOTES:
- ETFs like VOO, SPY, QQQ are valid US assets and should be classified as "us_assets"
- Indian ETFs like NIFTYBEES.NS are valid Indian assets and should be classified as "india_assets"
- Only flag as invalid if: (1) cryptocurrencies detected, (2) unsupported assets detected, or (3) mixing US and Indian assets
- Do NOT flag ETFs as "other" or invalid - they belong with their country's assets

Be thorough and accurate in your classification."""

        user_prompt = f"""Analyze these tickers and validate their country/exchange consistency:

Tickers: {tickers_str}

Determine:
1. Are all these valid assets - stocks and/or ETFs (no crypto/commodities/bonds)?
2. Do they all belong to the same country (all US or all India)?
3. Remember: ETFs from the same country as stocks are ALLOWED (e.g., AAPL + VOO is valid)
4. Provide detailed breakdown of each ticker.

Respond in the specified JSON format."""

        logger.info("Validating exchange consistency with LLM...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=GenerateContentConfig(
                system_instruction=[system_prompt]
            )
        )

        # Parse the LLM response
        if response and response.text:
            response_text = response.text.strip()
            logger.info(f"Exchange validation response: {response_text}")

            try:
                # Clean JSON response (remove markdown code blocks if present)
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                    response_text = response_text.strip()

                # Parse JSON
                validation_result = json.loads(response_text)
                is_valid = validation_result.get("is_valid", False)
                primary_exchange = validation_result.get("primary_exchange", "Unknown")
                invalid_assets = validation_result.get("invalid_assets", [])
                exchange_breakdown = validation_result.get("exchange_breakdown", {})
                llm_message = validation_result.get("message", "")

                logger.info(f"Validation result: valid={is_valid}, exchange={primary_exchange}")

                if is_valid:
                    # Additional validation: Check against user's market preference if provided
                    if user_market_preference:
                        # Normalize the user preference for comparison
                        user_pref_normalized = user_market_preference.upper()
                        if user_pref_normalized == "INDIA":
                            expected_exchange = "India"
                        elif user_pref_normalized == "US":
                            expected_exchange = "US"
                        else:
                            expected_exchange = None

                        # Validate that portfolio matches user's market preference
                        if expected_exchange and primary_exchange != expected_exchange:
                            error_message = "**Invalid Portfolio: Market Preference Mismatch**\n\n"
                            error_message += f"You selected **{user_market_preference} Market**, but your portfolio contains "
                            error_message += f"**{primary_exchange}** stocks.\n\n"
                            error_message += "**Requirement:** All stocks must match your selected market preference.\n"
                            if expected_exchange == "US":
                                error_message += "Please provide only US stocks (e.g., AAPL, GOOGL, MSFT, VOO, SPY).\n"
                            else:
                                error_message += "Please provide only Indian stocks (e.g., RELIANCE.NS, TCS.BO, INFY.NS).\n"

                            logger.warning(f"Portfolio exchange ({primary_exchange}) doesn't match user preference ({user_market_preference})")
                            return False, error_message, primary_exchange

                    message = f"All stocks validated successfully. Exchange: {primary_exchange}"
                    return True, message, primary_exchange
                else:
                    # Build detailed error message
                    message = "**Invalid Portfolio: Exchange Consistency Error**\n\n"

                    # Check for crypto/invalid assets
                    if invalid_assets:
                        message += "**Invalid Assets Detected:**\n"
                        for asset in invalid_assets:
                            ticker = asset.get('ticker', 'N/A')
                            asset_type = asset.get('type', 'unknown')
                            reason = asset.get('reason', 'Not supported')
                            message += f"• {ticker} - {asset_type}: {reason}\n"
                        message += "\n"

                    # Check for mixed exchanges
                    us_assets = exchange_breakdown.get("us_assets", [])
                    india_assets = exchange_breakdown.get("india_assets", [])

                    if us_assets and india_assets:
                        message += "**Mixed Countries Detected:**\n"
                        message += f"• US assets (stocks/ETFs): {', '.join(us_assets)}\n"
                        message += f"• Indian assets (stocks/ETFs): {', '.join(india_assets)}\n\n"
                        message += "**Requirement:** All assets must be from the SAME country.\n"
                        message += "Please provide either:\n"
                        message += "- All US assets only (e.g., AAPL, GOOGL, VOO, SPY), OR\n"
                        message += "- All Indian assets only (e.g., RELIANCE.NS, TCS.BO, NIFTYBEES.NS)\n"

                    # Check for crypto
                    crypto = exchange_breakdown.get("crypto", [])
                    if crypto:
                        message += f"\n**Cryptocurrency Detected:** {', '.join(crypto)}\n"
                        message += "Cryptocurrencies are not supported. Please provide only stock tickers.\n"

                    # Check for other assets
                    other = exchange_breakdown.get("other", [])
                    if other:
                        message += f"\n**Unsupported Assets:** {', '.join(other)}\n"
                        message += "Only stocks are supported (no commodities, forex, bonds, etc.)\n"

                    if llm_message:
                        message += f"\n**Details:** {llm_message}"

                    return False, message, primary_exchange

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse exchange validation JSON: {e}")
                logger.error(f"Response text: {response_text}")
                # If we can't parse, be lenient and allow through (backward compatibility)
                return True, "Could not fully validate exchange consistency, proceeding with analysis.", "Unknown"
        else:
            logger.error("No response from LLM for exchange validation")
            # If no response, be lenient and allow through
            return True, "Could not validate exchange consistency, proceeding with analysis.", "Unknown"

    except Exception as e:
        logger.error(f"Error validating exchange consistency: {e}")
        # On error, be lenient and allow through
        return True, f"Validation error, proceeding with analysis: {str(e)}", "Unknown"


def append_exchange_suffix(holdings_data: list, primary_exchange: str) -> list:
    """
    Appends appropriate exchange suffix to stock tickers based on the primary exchange.

    Args:
        holdings_data: List of holdings dictionaries with ticker symbols
        primary_exchange: The primary exchange ("US", "India", etc.)

    Returns:
        Modified holdings_data with exchange suffixes appended
    """
    try:
        if not holdings_data or not primary_exchange:
            return holdings_data

        logger.info(f"Appending exchange suffix for {primary_exchange} stocks")

        # Only modify if all stocks are from India
        if primary_exchange == "India":
            for holding in holdings_data:
                ticker = holding.get('ticker', '')
                if ticker:
                    # Check if ticker already has .NS or .BO suffix
                    if not ticker.endswith('.NS') and not ticker.endswith('.BO'):
                        # Append .NS suffix for NSE (National Stock Exchange)
                        holding['ticker'] = f"{ticker}.NS"
                        logger.info(f"Added .NS suffix: {ticker} -> {holding['ticker']}")

        # For US stocks, no suffix needed (US tickers don't have suffixes)
        # For foreign/other exchanges, keep as is

        return holdings_data

    except Exception as e:
        logger.error(f"Error appending exchange suffix: {e}")
        return holdings_data


def extract_stock_tickers_from_text(portfolio_text: str, user_market_preference: str = None) -> str:
    """
    Extracts stock tickers from portfolio text using LLM.
    Works with text from PDFs, images, or direct text input.

    Args:
        portfolio_text: The portfolio text (from any source)
        user_market_preference: User's chosen market preference ("US" or "INDIA"), if set

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

Your task is to carefully analyze portfolio text and extract ALL stock and ETF holdings with as much detail as possible.

EXTRACTION RULES:
1. Extract valid stock ticker symbols (1-5 characters, letters only)
2. Extract ETF ticker symbols (e.g., VOO, SPY, QQQ, VTI, NIFTYBEES.NS)
3. Convert company names to ticker symbols (e.g., "Apple Inc." → "AAPL")
4. Include BOTH individual stocks AND ETFs/index funds
5. Convert all tickers to uppercase
6. Extract SHARE QUANTITIES when explicitly mentioned
7. Extract dollar amounts invested when mentioned
8. Extract percentage allocations when mentioned
9. Do NOT include common words, currency codes, or non-stock identifiers
10. Do NOT include cryptocurrencies, commodities, or bonds

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

        # VALIDATE EXCHANGE CONSISTENCY - Must all be from same country (US or India), stocks + ETFs allowed from same country, no crypto
        # Also validates against user's market preference if provided
        is_valid, validation_message, primary_exchange = validate_exchange_consistency(holdings_data, user_market_preference)
        if not is_valid:
            logger.warning(f"Exchange validation failed: {validation_message}")
            return validation_message

        logger.info(f"Exchange validation passed: {validation_message}")

        # APPEND EXCHANGE SUFFIX - Add .NS for Indian stocks, keep US stocks as is
        if primary_exchange and primary_exchange != "Unknown":
            holdings_data = append_exchange_suffix(holdings_data, primary_exchange)
            logger.info(f"Applied exchange suffix for {primary_exchange} stocks")

        # Format the result with detailed holdings information
        result = f"**Portfolio Holdings Extracted:**\n\n"
        result += f"Total assets identified: {len(holdings_data)}\n\n"

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
