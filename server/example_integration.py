"""
Example: Complete integration of AI Input Processor with Test Generator.

This demonstrates the full pipeline:
1. Extract requirements from document using Gemini API
2. Generate UI test specs using LangChain + OpenAI
3. Execute tests with Selenium

Usage:
    export GOOGLE_API_KEY="your-gemini-key"
    export OPENAI_API_KEY="your-openai-key"
    python example_integration.py
"""

import os
from pathlib import Path

from ai_input_processor import process_document, to_ui_test_input
from langchain_openai import ChatOpenAI
from langchain_ui_test_pipeline import UITestEngineInput, run_langchain_ui_test_pipeline


def build_mock_ui_context(target_url: str) -> dict:
    """Build a mock UI context (in production, use Selenium crawler)."""
    return {
        "page_url": target_url,
        "title": "Example Login Page",
        "elements": [
            {
                "id": "email_input",
                "label": "Email",
                "css_selector": "input[name='email']",
            },
            {
                "id": "password_input",
                "label": "Password",
                "css_selector": "input[name='password']",
            },
            {
                "id": "login_button",
                "label": "Log in",
                "css_selector": "button[type='submit']",
            },
        ],
    }


def main():
    """Run the complete integration example."""
    # Check API keys
    if "GOOGLE_API_KEY" not in os.environ:
        print("❌ GOOGLE_API_KEY not set")
        return
    if "OPENAI_API_KEY" not in os.environ:
        print("❌ OPENAI_API_KEY not set")
        return

    print("🚀 Complete Integration Example")
    print("=" * 60)

    # Step 1: Process document with AI Input Processor (Gemini)
    document_path = "docs/PRD.md"  # Or any PDF/DOCX/MD/TXT file

    if not Path(document_path).exists():
        print(f"⚠️  Document not found: {document_path}")
        print("   Using mock extracted requirements instead...")
        # Mock extracted requirements
        extracted = {
            "overview": "Login feature for user authentication",
            "frontend_features": ["Login page", "Error messages", "Forgot password link"],
            "functional_requirements": [
                "User must be able to log in with email and password",
                "Invalid credentials should show error message",
            ],
            "non_functional_requirements": [
                "Login should complete within 3 seconds",
                "Page must be responsive on mobile and desktop",
            ],
            "user_flow_context": [
                "User navigates to login page",
                "User enters credentials and clicks submit",
                "User is redirected to dashboard on success",
            ],
        }
    else:
        print(f"\n📄 Step 1: Processing document: {document_path}")
        try:
            extracted = process_document(document_path)
            print("✅ Document processed successfully")
        except Exception as e:
            print(f"❌ Error processing document: {e}")
            return

    # Step 2: Build UI context (mock for this example)
    target_url = "https://example.com/login"
    ui_context = build_mock_ui_context(target_url)

    # Step 3: Convert to UITestEngineInput format
    print("\n🔄 Step 2: Converting to test generator input format")
    test_input_dict = to_ui_test_input(extracted, ui_context)
    payload = UITestEngineInput(**test_input_dict)

    # Step 4: Generate test spec with LangChain (OpenAI)
    print("\n🤖 Step 3: Generating test spec with LangChain")
    llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.0)

    try:
        test_specs = run_langchain_ui_test_pipeline(llm, payload)
        print(f"✅ Test suite generated successfully ({len(test_specs)} test cases)")
        print("\n=== Generated Test Suite ===")
        for idx, test_spec in enumerate(test_specs, 1):
            print(f"\n--- Test Case {idx}: {test_spec.test_name} ---")
            print(test_spec.model_dump_json(indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Error generating test suite: {e}")
        import traceback

        traceback.print_exc()
        return

    print("\n" + "=" * 60)
    print("✅ Integration example completed successfully!")
    print("\nNext steps:")
    print("  - Use the generated TestSpecs with your test executor")
    print("  - See run_langchain_ui_pipeline.py for execution example")


if __name__ == "__main__":
    main()
