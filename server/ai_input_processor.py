"""
AI Input Processor Service

Extracts structured UI testing requirements from documents (PDF, DOCX, MD, TXT)
using Google Gemini API directly (no LangChain).

Output format matches UITestEngineInput expected by langchain_ui_test_pipeline.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import chardet
import markdown
import pdfplumber
from bs4 import BeautifulSoup
from docx import Document
from pydantic import BaseModel, Field, ValidationError

# Import google.generativeai with better error handling
try:
    import google.generativeai as genai
except ImportError as e:
    raise ImportError(
        "Failed to import google.generativeai. "
        "Please install it with: pip install --upgrade google-generativeai\n"
        "If you encounter module errors, try: pip install --upgrade --force-reinstall google-generativeai"
    ) from e


# ---------------------------------------------------------------------------
# Pydantic Schema for Extracted Requirements
# ---------------------------------------------------------------------------


class ExtractedRequirements(BaseModel):
    """Structured output schema for document extraction."""

    overview: str = Field(
        ..., description="High-level overview of the application/feature"
    )
    frontend_features: List[str] = Field(
        ..., description="List of frontend features/UI components"
    )
    functional_requirements: List[str] = Field(
        ..., description="Functional frontend requirements"
    )
    non_functional_requirements: List[str] = Field(
        ..., description="Non-functional requirements (performance, accessibility, UX)"
    )
    user_flow_context: List[str] = Field(
        ..., description="User flow descriptions and context"
    )


# ---------------------------------------------------------------------------
# Document Loaders
# ---------------------------------------------------------------------------


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF using pdfplumber."""
    text_parts = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        return "\n\n".join(text_parts)
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {e}") from e


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        doc = Document(file_path)
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as e:
        raise ValueError(f"Failed to extract text from DOCX: {e}") from e


def extract_text_from_markdown(file_path: str) -> str:
    """Extract text from Markdown file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        html = markdown.markdown(md_content)
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n\n")
    except Exception as e:
        raise ValueError(f"Failed to extract text from Markdown: {e}") from e


def extract_text_from_txt(file_path: str) -> str:
    """Extract text from plain text file with encoding detection."""
    try:
        with open(file_path, "rb") as f:
            raw_data = f.read()
            encoding = chardet.detect(raw_data)["encoding"]
        with open(file_path, "r", encoding=encoding or "utf-8") as f:
            return f.read()
    except Exception as e:
        raise ValueError(f"Failed to extract text from TXT: {e}") from e


def detect_and_extract(file_path: str) -> str:
    """
    Auto-detect file format and extract text.

    Args:
        file_path: Path to the document file

    Returns:
        Extracted text content

    Raises:
        ValueError: If file format is unsupported
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_text_from_pdf(file_path)
    elif suffix == ".docx":
        return extract_text_from_docx(file_path)
    elif suffix in [".md", ".markdown"]:
        return extract_text_from_markdown(file_path)
    elif suffix == ".txt":
        return extract_text_from_txt(file_path)
    else:
        raise ValueError(
            f"Unsupported file format: {suffix}. Supported: .pdf, .docx, .md, .txt"
        )


# ---------------------------------------------------------------------------
# Text Preprocessing
# ---------------------------------------------------------------------------


def preprocess_text(text: str) -> str:
    """
    Clean and normalize extracted text.

    - Normalize whitespace
    - Remove excessive newlines
    - Remove common headers/footers patterns
    """
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove common headers/footers patterns
    text = re.sub(r"Page \d+ of \d+", "", text)
    text = re.sub(r"^\d+\s*$", "", text, flags=re.MULTILINE)  # Remove page numbers
    return text.strip()


# ---------------------------------------------------------------------------
# Gemini API Integration
# ---------------------------------------------------------------------------


SYSTEM_PROMPT = """You are an expert QA analyst and test designer. 
Your task is to extract UI-testing-relevant information from user-provided documentation and transform it into a structured JSON format suitable for automated test generation.

You should only extract information relevant to:

- Functional requirements that affect the UI (e.g., user actions, forms, buttons, navigation, interactive elements)
- Non-functional requirements that affect user interactions or UI behavior (e.g., page responsiveness, load time, accessibility)
- User flows describing sequences of interactions or page transitions
- UX context that informs interface behavior (e.g., feature purpose, screen hierarchy)

You must IGNORE:

- Backend implementation details (databases, APIs, authentication logic)
- Deployment, hosting, server-side architecture
- Security protocols unrelated to UI (encryption methods, JWTs)
- Performance metrics not observable through the UI (server CPU, DB response time)
- Marketing or product strategy content
- Any content unrelated to the UI or user experience

Output MUST be valid JSON ONLY and follow the specified schema below. Do not include explanations, summaries, or additional text. Only extract information that is explicitly present in the document. Do not hallucinate or invent requirements."""

DEVELOPER_PROMPT = """Rules:
1. Extract only what is explicitly stated in the document.
2. Organize functional requirements as individual items in "functional_requirements" array.
3. Non-functional requirements (performance, accessibility, responsiveness) go into "non_functional_requirements" array.
4. User flows should be described as sequential steps in "user_flow_context" array.
5. Frontend features should list UI components, pages, or major features.
6. Overview should be a concise summary paragraph.
7. Output valid JSON only - no markdown, no code blocks, no explanations.
8. If a section is missing, return empty array [] or empty string "".
9. Ensure all arrays are lists, even if empty."""

USER_PROMPT_TEMPLATE = """DOCUMENT TEXT:
{document_text}

Extract overview, frontend features, functional requirements, non-functional requirements, and user flow context. Output as JSON matching this exact schema:

{{
  "overview": "string",
  "frontend_features": ["string"],
  "functional_requirements": ["string"],
  "non_functional_requirements": ["string"],
  "user_flow_context": ["string"]
}}"""


def build_extraction_prompt(document_text: str) -> str:
    """Build the complete prompt for Gemini."""
    return f"{SYSTEM_PROMPT}\n\n{DEVELOPER_PROMPT}\n\n{USER_PROMPT_TEMPLATE.format(document_text=document_text)}"


def extract_with_gemini(
    document_text: str,
    api_key: Optional[str] = None,
    model_name: str = "gemini-2.5-flash",
    temperature: float = 0.0,
    max_retries: int = 2,
) -> ExtractedRequirements:
    """
    Extract structured requirements using Gemini API.

    Args:
        document_text: Preprocessed document text
        api_key: Google API key (if None, uses GOOGLE_API_KEY env var)
        model_name: Gemini model name (default: "gemini-2.5-flash")
        temperature: Sampling temperature (0.0 for deterministic)
        max_retries: Maximum retry attempts on validation failure

    Returns:
        ExtractedRequirements Pydantic model

    Raises:
        ValueError: If extraction fails after retries
        RuntimeError: If API key is missing
    """
    # Initialize Gemini client
    api_key = api_key or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY not found. Set it in environment or pass as argument."
        )

    genai.configure(api_key=api_key)

    # Build prompt with explicit JSON format instructions
    prompt = build_extraction_prompt(document_text)
    # Add explicit JSON instruction at the end
    prompt += "\n\nIMPORTANT: Output ONLY valid JSON. Do not include markdown code blocks, explanations, or any other text."

    # Configure generation config (without response_mime_type for compatibility)
    try:
        # Try with response_mime_type if available (newer versions)
        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            response_mime_type="application/json",
        )
    except TypeError:
        # Fallback for older versions that don't support response_mime_type
        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
        )

    # Try to create model with better error handling
    try:
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        error_msg = f"Model '{model_name}' not found or not supported."
        error_msg += "\nCommon models: 'gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro'"
        raise ValueError(error_msg) from e

    # Try extraction with retries
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = model.generate_content(
                prompt,
                generation_config=generation_config,
            )

            # Extract JSON from response
            response_text = response.text.strip()

            # Handle markdown code blocks if present
            if "```json" in response_text:
                # Extract content between ```json and ```
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                if end != -1:
                    response_text = response_text[start:end].strip()
            elif response_text.startswith("```"):
                # Remove markdown code block markers (generic)
                lines = response_text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response_text = "\n".join(lines).strip()
            
            # Try to find JSON object boundaries if there's extra text
            if not response_text.startswith("{"):
                # Look for first { and last }
                start_idx = response_text.find("{")
                end_idx = response_text.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    response_text = response_text[start_idx:end_idx + 1]

            # Parse JSON
            try:
                json_data = json.loads(response_text)
            except json.JSONDecodeError as e:
                if attempt < max_retries:
                    # Add error feedback to prompt for retry
                    prompt = f"{prompt}\n\nPrevious attempt failed JSON parsing: {str(e)}\n\nPlease output valid JSON only."
                    last_error = e
                    continue
                raise ValueError(f"Failed to parse JSON response: {e}") from e

            # Validate against Pydantic schema
            try:
                result = ExtractedRequirements(**json_data)
                return result
            except ValidationError as e:
                if attempt < max_retries:
                    # Add validation error feedback for retry
                    prompt = f"{prompt}\n\nPrevious attempt failed validation: {str(e)}\n\nPlease ensure the JSON matches the schema exactly."
                    last_error = e
                    continue
                raise ValueError(f"Validation failed: {e}") from e

        except Exception as e:
            if attempt < max_retries:
                last_error = e
                continue
            raise ValueError(f"Gemini API call failed: {e}") from e

    # If we exhausted retries
    raise ValueError(f"Extraction failed after {max_retries + 1} attempts. Last error: {last_error}")


# ---------------------------------------------------------------------------
# Main Public API
# ---------------------------------------------------------------------------


def process_document(
    file_path: str,
    api_key: Optional[str] = None,
    model_name: str = "gemini-2.5-flash",
    temperature: float = 0.0,
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    Main entry point: extract text from document and process with Gemini.

    Args:
        file_path: Path to document (PDF, DOCX, MD, TXT)
        api_key: Google API key (optional, uses env var if not provided)
        model_name: Gemini model name (default: "gemini-2.5-flash")
        temperature: Sampling temperature
        max_retries: Maximum retry attempts

    Returns:
        Dictionary with keys: overview, frontend_features, functional_requirements,
        non_functional_requirements, user_flow_context

    Example:
        >>> result = process_document("requirements.pdf")
        >>> print(result["functional_requirements"])
    """
    # 1. Extract text from document
    raw_text = detect_and_extract(file_path)

    # 2. Preprocess text
    cleaned_text = preprocess_text(raw_text)

    # 3. Extract structured requirements with Gemini
    result = extract_with_gemini(
        cleaned_text,
        api_key=api_key,
        model_name=model_name,
        temperature=temperature,
        max_retries=max_retries,
    )

    # 4. Return as dict (JSON-serializable)
    return result.model_dump()


def process_text(
    text: str,
    api_key: Optional[str] = None,
    model_name: str = "gemini-2.5-flash",
    temperature: float = 0.0,
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    Process raw text directly (useful for text already extracted).

    Args:
        text: Raw document text
        api_key: Google API key (optional)
        model_name: Gemini model name (default: "gemini-2.5-flash")
        temperature: Sampling temperature
        max_retries: Maximum retry attempts

    Returns:
        Dictionary with extracted requirements
    """
    cleaned_text = preprocess_text(text)
    result = extract_with_gemini(
        cleaned_text,
        api_key=api_key,
        model_name=model_name,
        temperature=temperature,
        max_retries=max_retries,
    )
    return result.model_dump()


# ---------------------------------------------------------------------------
# Integration Helper
# ---------------------------------------------------------------------------


def to_ui_test_input(
    extracted: Dict[str, Any],
    ui_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Convert extracted requirements to UITestEngineInput format.

    This helper maps the output of process_document() to the format expected
    by langchain_ui_test_pipeline.UITestEngineInput.

    Args:
        extracted: Output from process_document()
        ui_context: UI context dictionary (from Selenium crawler)

    Returns:
        Dictionary ready for UITestEngineInput construction
    """
    from langchain_ui_test_pipeline import UITestEngineInput

    return {
        "ui_context": ui_context,
        "functional_requirements": extracted.get("functional_requirements", []),
        "non_functional_requirements": extracted.get("non_functional_requirements", []),
        "user_flow_context": extracted.get("user_flow_context", []),
        "overview": extracted.get("overview"),
        "frontend_features": extracted.get("frontend_features"),
    }


__all__ = [
    "ExtractedRequirements",
    "process_document",
    "process_text",
    "detect_and_extract",
    "preprocess_text",
    "to_ui_test_input",
]
