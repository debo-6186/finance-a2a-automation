import logging
from typing import Any, Literal, Union
from pydantic import BaseModel
import google.genai as genai
import fitz  # PyMuPDF
from logger import get_logger
import os

logger = get_logger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

class ResponseFormat(BaseModel):
    """Respond to the user in this format."""
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str

class StockReportAnalyserAgent:
    """Agent for analyzing PDF stock reports using Gemini (google.genai)."""

    SYSTEM_INSTRUCTION = (
        "You are a financial analysis assistant. Your job is to analyze PDF stock reports provided by the user. "
        "Check the allocation percentage of the stock in the portfolio. "
        "Summarize your findings in clear, concise Markdown. Do not invent information."
    )

    RESPONSE_FORMAT_INSTRUCTION = (
        'Select status as "completed" if the request is fully addressed and no further input is needed. '
        'Select status as "input_required" if you need more information from the user or are asking a clarifying question. '
        'Select status as "error" if an error occurred or the request cannot be fulfilled.'
    )

    def __init__(self):
        try:
            self.genai_client = genai.Client()
            self.model_name = "gemini-2.5-flash-preview-04-17"
            logger.info("google.genai Client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize google.genai Client: {e}", exc_info=True)
            raise

    def extract_text_from_pdf(self, pdf_data: Union[str, bytes]) -> str:
        """
        Extracts text from a PDF file given a file path or bytes using fitz (PyMuPDF).
        """
        try:
            if isinstance(pdf_data, str):
                logger.info(f"Opening PDF file: {pdf_data}")
                doc = fitz.open(pdf_data)
            else:
                doc = fitz.open(stream=pdf_data, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            logger.info(f"Extracted {len(text)} characters from PDF using fitz.")
            return text
        except Exception as e:
            logger.error(f"Error extracting text from PDF with fitz: {e}", exc_info=True)
            raise

    async def analyze_pdf(self, pdf_data: Union[str, bytes], session_id: str = None) -> dict[str, Any]:
        """
        Analyzes a PDF stock report and returns a structured response.
        Args:
            pdf_data: Path to PDF file or bytes.
            session_id: Optional session identifier.
        Returns:
            dict with keys: is_task_complete, require_user_input, content
        """
        if not pdf_data:
            return {
                "is_task_complete": False,
                "require_user_input": True,
                "content": "No PDF file provided. Please upload a stock report PDF.",
            }
        try:
            text = self.extract_text_from_pdf(pdf_data)
            if not text.strip():
                return {
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": "The PDF appears to be empty or could not be read.",
                }
            prompt = f"""
{self.SYSTEM_INSTRUCTION}\n\nPDF Content:\n{text[:24000]}\n\n{self.RESPONSE_FORMAT_INSTRUCTION}\nRespond in the specified format."
            """
            # Gemini API call
            response = self.genai_client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "temperature": 0.2,
                    "max_output_tokens": 4096,
                }
            )
            # Try to parse as ResponseFormat
            try:
                result = ResponseFormat.parse_raw(response.text)
                status = result.status
                message = result.message
            except Exception:
                status = "completed"
                message = response.text
            return {
                "is_task_complete": status == "completed",
                "require_user_input": status == "input_required",
                "content": message,
            }
        except Exception as e:
            logger.error(f"Error in analyze_pdf: {e}", exc_info=True)
            return {
                "is_task_complete": True,
                "require_user_input": False,
                "content": f"An error occurred while analyzing the PDF: {str(e)}",
            }
