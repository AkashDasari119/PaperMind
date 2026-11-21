import base64
import os
import sys
import time
from os.path import dirname as up
from typing import Generator, Union

sys.path.append(os.path.abspath(os.path.join(up(__file__), os.pardir)))

from dotenv import load_dotenv
from google import genai
from google.genai import types

from research_paper_analyst import FOLLOWUP_CONTEXT, RESEARCH_PAPER

load_dotenv()


def get_api_key(provided_key: str = None) -> str:
    """Resolve API key from parameter or environment variables."""
    if provided_key and provided_key.strip():
        return provided_key.strip()
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""


def initialize_gemini(api_key: str = None):
    """Initialize and return the Gemini client."""
    resolved_key = get_api_key(api_key)
    if not resolved_key:
        return None
    try:
        client = genai.Client(api_key=resolved_key)
        return client
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Gemini client: {str(e)}")


def _prepare_pdf_part(pdf_content: Union[bytes, str]) -> types.Part:
    """Convert raw bytes or base64 string into a types.Part object."""
    if isinstance(pdf_content, str):
        raw_bytes = base64.b64decode(pdf_content)
    elif isinstance(pdf_content, bytes):
        raw_bytes = pdf_content
    else:
        raise ValueError("Invalid PDF content format; expected bytes or base64 string.")
    return types.Part.from_bytes(data=raw_bytes, mime_type="application/pdf")


def is_transient_error(e: Exception) -> bool:
    """Check if exception represents a temporary 503 or 429 server error."""
    err_str = str(e).lower()
    return any(
        code in err_str
        for code in ["503", "unavailable", "high demand", "resource_exhausted", "429"]
    )


def analyze_pdf_content(
    client,
    model_name: str,
    pdf_content: Union[bytes, str],
    max_retries: int = 3,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
):
    """Analyze the given PDF content with exponential backoff on transient errors."""
    pdf_part = _prepare_pdf_part(pdf_content)
    delay = initial_delay

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content_stream(
                model=model_name,
                contents=[pdf_part, RESEARCH_PAPER],
            )
            has_yielded = False
            for chunk in response:
                if hasattr(chunk, "text") and chunk.text:
                    has_yielded = True
                    yield chunk.text
            return
        except Exception as e:
            if is_transient_error(e) and attempt < max_retries and not has_yielded:
                time.sleep(delay)
                delay *= backoff_factor
                continue
            raise e


def process_query_stream(
    client,
    model_name: str,
    pdf_content: Union[bytes, str],
    notes: str,
    query: str,
    max_retries: int = 3,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
):
    """Process a user query against the analyzed PDF content with exponential backoff."""
    pdf_part = _prepare_pdf_part(pdf_content)
    context = f"{notes}\n\n{FOLLOWUP_CONTEXT}\n\n{query}"
    delay = initial_delay

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content_stream(
                model=model_name,
                contents=[pdf_part, context],
            )
            has_yielded = False
            for chunk in response:
                if hasattr(chunk, "text") and chunk.text:
                    has_yielded = True
                    yield chunk.text
            return
        except Exception as e:
            if is_transient_error(e) and attempt < max_retries and not has_yielded:
                time.sleep(delay)
                delay *= backoff_factor
                continue
            raise e


