"""
Test script for AI Input Processor using Gemini API directly.

Usage:
    export GOOGLE_API_KEY="your-key"
    python test_ai_input_processor.py
"""

import json
import os
from pathlib import Path

from ai_input_processor import process_document, process_text


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


def test_with_file(file_path: str):
    """Test with an actual document file."""
    if not Path(file_path).exists():
        print(f"⚠️  File not found: {file_path}")
        print("   Skipping file-based test")
        return

    print(f"\nTesting with file: {file_path}")
    print("=" * 60)

    try:
        result = process_document(file_path)
        print("\n=== Extracted Requirements ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("\n✅ File processing successful")
    except Exception as e:
        print(f"\n❌ Error processing file: {e}")


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
        "sample_requirements.pdf",
        "sample_requirements.docx",
        "sample_requirements.md",
        "requirements.md",
        "/Users/aruzhan/Desktop/PANIO/panio-app/README.md"
    ]

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
