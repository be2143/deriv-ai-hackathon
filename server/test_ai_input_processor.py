"""
Test script for AI Input Processor using Gemini API directly.

Usage:
    export GOOGLE_API_KEY="your-key"
    python test_ai_input_processor.py
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from ai_input_processor import process_document, process_text


def save_extracted_requirements(result: dict, source: str = "mock", save_to_reports: bool = True) -> Optional[Path]:
    """
    Save extracted requirements JSON to reports folder.
    
    Args:
        result: Extracted requirements dictionary
        source: Source identifier (filename or "mock")
        save_to_reports: Whether to save the file
    
    Returns:
        Path to saved file or None if not saved
    """
    if not save_to_reports:
        return None
    
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create safe filename from source
    if source != "mock":
        safe_name = Path(source).stem
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", safe_name)[:50]
    else:
        safe_name = "mock"
    
    filename = f"extracted_requirements_{safe_name}_{timestamp}.json"
    file_path = reports_dir / filename
    
    # Add metadata to the result
    output_json = {
        "extracted_at": datetime.now().isoformat(),
        "source": source,
        "requirements": result,
    }
    
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(output_json, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Extracted requirements saved to: {file_path}")
    return file_path


def test_with_mock_text():
    """Test with mock document text."""
    mock_document = """
# Login Feature Specification

## Overview
The login feature allows users to authenticate and access the dashboard.

## Frontend Features
- Login page with email and password fields
- Forgot password link
- Error message display area
- Remember me checkbox

## Functional Requirements
- Users must be able to log in using email and password
- Form validation should show errors inline
- Invalid credentials should display an error message
- Successful login redirects to dashboard

## Non-functional Requirements
- Login should complete within 3 seconds under normal conditions
- Page must be responsive on mobile and desktop devices
- Error messages must meet WCAG AA contrast standards
- Form should be accessible via keyboard navigation

## User Flow
1. User navigates to login page from homepage
2. User enters email address
3. User enters password
4. User clicks "Log in" button
5. System validates credentials
6. On success, user is redirected to dashboard
7. On failure, error message is displayed
"""

    print("Testing with mock text...")
    print("=" * 60)

    result = process_text(mock_document)

    print("\n=== Extracted Requirements ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Verify structure
    assert "overview" in result
    assert "frontend_features" in result
    assert "functional_requirements" in result
    assert "non_functional_requirements" in result
    assert "user_flow_context" in result

    print("\n✅ All fields present in output")
    print(f"  - Overview: {len(result['overview'])} chars")
    print(f"  - Frontend Features: {len(result['frontend_features'])} items")
    print(f"  - Functional Requirements: {len(result['functional_requirements'])} items")
    print(f"  - Non-functional Requirements: {len(result['non_functional_requirements'])} items")
    print(f"  - User Flow Context: {len(result['user_flow_context'])} items")
    
    # Save to reports folder
    save_extracted_requirements(result, source="mock")


def test_with_file(file_path: str):
    """Test with an actual document file."""
    if not Path(file_path).exists():
        print(f"⚠️  File not found: {file_path}")
        print("   Skipping file-based test")
        return

    print(f"\nTesting with file: {file_path}")
    print("=" * 60)

    try:
        # First, verify file exists and check its size
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            print(f"❌ File not found: {file_path}")
            return
        
        file_size = file_path_obj.stat().st_size
        print(f"📁 File size: {file_size} bytes")
        
        # Check what text is extracted
        from ai_input_processor import detect_and_extract, preprocess_text
        print(f"🔄 Extracting text from: {file_path}")
        raw_text = detect_and_extract(file_path)
        print(f"📄 Raw extracted text length: {len(raw_text)} characters")
        
        if len(raw_text) == 0:
            print("⚠️  WARNING: Raw text extraction returned 0 characters!")
            print("   Trying to read file directly...")
            with open(file_path, "r", encoding="utf-8") as f:
                direct_read = f.read()
            print(f"   Direct file read length: {len(direct_read)} characters")
            print(f"   First 200 chars: {direct_read[:200]}")
            return
        
        cleaned_text = preprocess_text(raw_text)
        print(f"📄 Cleaned text length: {len(cleaned_text)} characters")
        print(f"📄 First 500 chars: {cleaned_text[:500]}...")
        
        result = process_document(file_path)
        print("\n=== Extracted Requirements ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Check if extraction was successful
        if not result.get("overview") and not result.get("functional_requirements"):
            print("\n⚠️  WARNING: Extraction returned empty results!")
            print("   This might indicate:")
            print("   - The document structure doesn't match expected format")
            print("   - The LLM didn't find relevant sections")
            print("   - There was an issue with the API call")
        
        print("\n✅ File processing successful")
        
        # Save to reports folder
        save_extracted_requirements(result, source=file_path)
    except Exception as e:
        print(f"\n❌ Error processing file: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main test runner."""
    if "GOOGLE_API_KEY" not in os.environ:
        print("❌ GOOGLE_API_KEY not set in environment")
        print("   Please set it before running:")
        print("   export GOOGLE_API_KEY='your-key'")
        return

    print("🚀 AI Input Processor Test Suite")
    print("=" * 60)

    # # Test 1: Mock text
    # try:
    #     test_with_mock_text()
    # except Exception as e:
    #     print(f"\n❌ Mock text test failed: {e}")
    #     import traceback

    #     traceback.print_exc()
    #     return

    # Test 2: Try to find sample files
    sample_files = [
        "/Users/aruzhan/Desktop/deriv-ai-hackathon/test_scripts/prd_random_org.md"
        
    ]
    
    #  "/Users/aruzhan/Desktop/PANIO/panio-app/README.md"

    for file_path in sample_files:
        if Path(file_path).exists():
            try:
                test_with_file(file_path)
                break
            except Exception as e:
                print(f"\n⚠️  Error with {file_path}: {e}")
                continue

    print("\n" + "=" * 60)
    print("✅ Test suite completed")


if __name__ == "__main__":
    main()
