import argparse
import os
import sys

from dotenv import load_dotenv

from ai_qa_pipeline import AIQAPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the AI QA pipeline against a URL.")
    parser.add_argument(
        "--url",
        required=True,
        help="Target URL to test, e.g. https://example.com",
    )
    parser.add_argument(
        "--tests",
        type=int,
        default=8,
        help="Number of AI-generated test cases to run (default: 8).",
    )
    parser.add_argument(
        "--headless",
        dest="headless",
        action="store_true",
        help="Run the browser in headless mode (default).",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Run the browser with a visible window (if supported).",
    )
    parser.set_defaults(headless=True)
    return parser.parse_args()


def main() -> None:
    # Load variables from .env (if present) before reading OPENAI_API_KEY
    load_dotenv()

    args = parse_args()

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("ERROR: OPENAI_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    # Ensure output directories exist
    os.makedirs("screenshots", exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    pipeline = AIQAPipeline(openai_api_key)
    results, report_path = pipeline.run_pipeline(
        url=args.url,
        num_tests=args.tests,
        headless=args.headless,
    )

    print("\n" + "=" * 50)
    print("🏁 TEST EXECUTION COMPLETE")
    print("=" * 50)

    for result in results:
        status_icon = "✅" if result.status == "PASS" else "❌"
        print(f"{status_icon} {result.test_case.name}")
        if result.error_message:
            print(f"   Error: {result.error_message[:200]}...")

    print(f"\nReport saved at: {report_path}")


if __name__ == "__main__":
    main()


