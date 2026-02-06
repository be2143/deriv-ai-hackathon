# AI Input Processor Specification

## 1. Purpose

The AI Input Processor is responsible for:
- Accepting various input formats (PDF, Markdown, plain text, Word documents)
- Extracting text content using specific Python libraries
- Using an LLM to extract structured UI testing information:
  - Overview
  - Frontend features
  - Functional frontend requirements
  - Non-functional frontend requirements
  - User flows
- Transforming the extracted information into a structured JSON format compatible with the downstream test generator agent (`langchain_ui_test_pipeline`)

This enables users to submit documentation in any format without manual preprocessing, and automatically structures it for UI test generation.

---

## 2. Technology Stack

### 2.1 Document Extraction Libraries

| Format | Library | Installation | Notes |
|--------|---------|--------------|-------|
| **PDF** | `pdfplumber` or `PyPDF2` | `pip install pdfplumber` | `pdfplumber` preferred for better text extraction and table handling |
| **DOCX** | `python-docx` | `pip install python-docx` | Handles Word documents (.docx) |
| **Markdown** | `markdown` | `pip install markdown` | Parse MD to HTML, then extract text |
| **Plain Text** | Built-in | N/A | Direct file reading with encoding detection |

### 2.2 AI Processing

- **LangChain**: For LLM orchestration and structured output
- **Pydantic**: For JSON schema validation
- **LLM Provider**: OpenAI (ChatOpenAI) or compatible LangChain provider

---

## 3. Architecture & Workflow

### 3.1 High-Level Workflow

```
User submits document(s) (PDF, DOCX, MD, TXT)
        ↓
Document Loader (format-specific extraction)
  - PDF → pdfplumber
  - DOCX → python-docx
  - MD → markdown + BeautifulSoup
  - TXT → direct read
        ↓
Text Preprocessing
  - Clean whitespace
  - Remove headers/footers
  - Normalize formatting
        ↓
LangChain Extraction Chain
  - System prompt (QA analyst role)
  - Structured output (Pydantic model)
  - Extract: overview, features, requirements, flows
        ↓
JSON Validator
  - Validate against schema
  - Retry with corrective prompt if needed
        ↓
Structured JSON Output
        ↓
Downstream Test Generator Agent
  (langchain_ui_test_pipeline)
```

### 3.2 Component Breakdown

#### 3.2.1 Document Loader

**PDF Extraction (pdfplumber):**
```python
import pdfplumber

def extract_text_from_pdf(file_path: str) -> str:
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
    return "\n\n".join(text_parts)
```

**DOCX Extraction (python-docx):**
```python
from docx import Document

def extract_text_from_docx(file_path: str) -> str:
    doc = Document(file_path)
    paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
    return "\n\n".join(paragraphs)
```

**Markdown Extraction:**
```python
import markdown
from bs4 import BeautifulSoup

def extract_text_from_markdown(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    html = markdown.markdown(md_content)
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(separator='\n\n')
```

**Plain Text Extraction:**
```python
import chardet

def extract_text_from_txt(file_path: str) -> str:
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        encoding = chardet.detect(raw_data)['encoding']
    with open(file_path, 'r', encoding=encoding or 'utf-8') as f:
        return f.read()
```

#### 3.2.2 Text Preprocessing

```python
import re

def preprocess_text(text: str) -> str:
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove common headers/footers patterns (customize as needed)
    text = re.sub(r'Page \d+ of \d+', '', text)
    return text.strip()
```

#### 3.2.3 LangChain Extraction Chain

**Pydantic Schema:**
```python
from pydantic import BaseModel, Field
from typing import List

class ExtractedRequirements(BaseModel):
    overview: str = Field(..., description="High-level overview of the application/feature")
    frontend_features: List[str] = Field(..., description="List of frontend features/UI components")
    functional_requirements: List[str] = Field(..., description="Functional frontend requirements")
    non_functional_requirements: List[str] = Field(..., description="Non-functional requirements (performance, accessibility, UX)")
    user_flow_context: List[str] = Field(..., description="User flow descriptions and context")
```

**System Prompt:**
```
You are an expert QA analyst specializing in frontend UI testing. Your job is to read product documentation and extract information relevant to UI testing.

Extract:
1. **Overview**: High-level description of the application or feature
2. **Frontend Features**: List of UI components, pages, or features mentioned
3. **Functional Requirements**: What the UI must do (user actions, validations, behaviors)
4. **Non-functional Requirements**: Performance, accessibility, responsiveness, UX expectations
5. **User Flow Context**: Step-by-step user journeys and interaction flows

You must output valid JSON matching the provided schema. Only extract information that is explicitly present in the document. Do not hallucinate or invent requirements.
```

**Developer Prompt:**
```
Rules:
1. Extract only what is explicitly stated in the document.
2. Organize functional requirements as individual items in "functional_requirements" array.
3. Non-functional requirements (performance, accessibility, responsiveness) go into "non_functional_requirements" array.
4. User flows should be described as sequential steps in "user_flow_context" array.
5. Frontend features should list UI components, pages, or major features.
6. Overview should be a concise summary paragraph.
7. Output valid JSON only - no markdown, no code blocks, no explanations.
8. If a section is missing, return empty array [] or empty string "".
```

**User Prompt Template:**
```
DOCUMENT TEXT:
{document_text}

Extract overview, frontend features, functional requirements, non-functional requirements, and user flow context. Output as JSON matching the schema.
```

---

## 4. Output JSON Schema

The processor outputs JSON matching this structure (compatible with `UITestEngineInput`):

```json
{
  "overview": "Brief description of the application/feature",
  "frontend_features": [
    "Feature 1",
    "Feature 2"
  ],
  "functional_requirements": [
    "User must be able to log in with email and password",
    "Form validation shows errors inline"
  ],
  "non_functional_requirements": [
    "Login should complete within 3 seconds",
    "Page must be responsive on mobile and desktop",
    "Error messages must meet WCAG AA contrast standards"
  ],
  "user_flow_context": [
    "User navigates to login page from homepage",
    "User enters credentials and clicks submit",
    "User is redirected to dashboard on success"
  ]
}
```

**Note:** This output is then mapped to `UITestEngineInput`:
- `functional_requirements` → `functional_requirements` (direct mapping)
- `non_functional_requirements` → `non_functional_requirements` (direct mapping)
- `user_flow_context` → `user_flow_context` (direct mapping)
- `overview` and `frontend_features` can be included in the prompt context or stored for reference

---

## 5. Implementation Example

### 5.1 Complete Pipeline Code

```python
from typing import Dict, Any
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field, ValidationError
import pdfplumber
from docx import Document
import markdown
from bs4 import BeautifulSoup
import chardet
import re

# Pydantic schema (as defined above)
class ExtractedRequirements(BaseModel):
    overview: str
    frontend_features: List[str]
    functional_requirements: List[str]
    non_functional_requirements: List[str]
    user_flow_context: List[str]

# Document loaders (as defined above)
def extract_text_from_pdf(file_path: str) -> str:
    # ... implementation above

def extract_text_from_docx(file_path: str) -> str:
    # ... implementation above

def extract_text_from_markdown(file_path: str) -> str:
    # ... implementation above

def extract_text_from_txt(file_path: str) -> str:
    # ... implementation above

def detect_and_extract(file_path: str) -> str:
    """Auto-detect format and extract text."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    
    if suffix == '.pdf':
        return extract_text_from_pdf(file_path)
    elif suffix == '.docx':
        return extract_text_from_docx(file_path)
    elif suffix in ['.md', '.markdown']:
        return extract_text_from_markdown(file_path)
    elif suffix == '.txt':
        return extract_text_from_txt(file_path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

def preprocess_text(text: str) -> str:
    # ... implementation above

# LangChain chain
SYSTEM_PROMPT = """You are an expert QA analyst specializing in frontend UI testing..."""
DEVELOPER_PROMPT = """Rules: 1. Extract only what is explicitly stated..."""
USER_PROMPT = """DOCUMENT TEXT:\n{document_text}\n\nExtract overview, frontend features..."""

def build_extraction_chain(llm: ChatOpenAI) -> Runnable:
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("system", DEVELOPER_PROMPT),
        ("user", USER_PROMPT),
    ])
    return prompt | llm.with_structured_output(ExtractedRequirements)

def process_document(file_path: str, llm: ChatOpenAI) -> Dict[str, Any]:
    """Main entry point: extract text, process with LLM, return structured JSON."""
    # 1. Extract text
    raw_text = detect_and_extract(file_path)
    
    # 2. Preprocess
    cleaned_text = preprocess_text(raw_text)
    
    # 3. Build chain and invoke
    chain = build_extraction_chain(llm)
    result = chain.invoke({"document_text": cleaned_text})
    
    # 4. Return as dict (JSON-serializable)
    return result.model_dump()
```

### 5.2 Usage

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.0)
result = process_document("requirements.pdf", llm)

# Result is a dict with keys:
# - overview
# - frontend_features
# - functional_requirements
# - non_functional_requirements
# - user_flow_context

# Map to UITestEngineInput format:
from langchain_ui_test_pipeline import UITestEngineInput

payload = UITestEngineInput(
    ui_context=ui_context_dict,  # from Selenium crawler
    functional_requirements=result["functional_requirements"],
    non_functional_requirements=result["non_functional_requirements"],
    user_flow_context=result["user_flow_context"],
)
```

---

## 6. Error Handling & Validation

### 6.1 Schema Validation

- Use Pydantic's `ValidationError` to catch malformed LLM output
- Retry with a corrective prompt if validation fails:

```python
def process_with_retry(file_path: str, llm: ChatOpenAI, max_retries: int = 1) -> Dict[str, Any]:
    raw_text = detect_and_extract(file_path)
    cleaned_text = preprocess_text(raw_text)
    chain = build_extraction_chain(llm)
    
    try:
        result = chain.invoke({"document_text": cleaned_text})
        return result.model_dump()
    except ValidationError as e:
        if max_retries > 0:
            # Build retry prompt with error details
            retry_prompt = f"""Previous extraction failed validation:\n{str(e)}\n\nDocument:\n{cleaned_text}\n\nPlease correct the output."""
            result = chain.invoke({"document_text": retry_prompt})
            return result.model_dump()
        raise
```

### 6.2 File Format Errors

- Handle unsupported formats gracefully
- Provide clear error messages
- Support multiple encoding detection for text files

---

## 7. Integration with Test Generator

The output of this processor feeds directly into `langchain_ui_test_pipeline`:

```
Document → AI Input Processor → ExtractedRequirements JSON
                                        ↓
                            Map to UITestEngineInput
                                        ↓
                            langchain_ui_test_pipeline
                                        ↓
                            TestSpec JSON
                                        ↓
                            Test Code Generator
                                        ↓
                            Selenium Execution
```

---

## 8. Dependencies

Add to `requirements.txt`:

```
pdfplumber>=0.10.0
python-docx>=1.0.0
markdown>=3.5.0
beautifulsoup4>=4.12.0
chardet>=5.2.0
langchain>=0.1.0
langchain-openai>=0.0.5
pydantic>=2.0.0
```

---

## 9. Summary

The AI Input Processor:
- Uses **specific Python libraries** (`pdfplumber`, `python-docx`, `markdown`) for reliable text extraction
- Leverages **LangChain + Pydantic** for structured LLM extraction
- Outputs **JSON matching the test generator's expected format**
- Handles **multiple document formats** seamlessly
- Provides **validation and retry logic** for robust extraction

This creates a complete pipeline: **Document → Structured Requirements → Test Specs → Executable Tests**.
