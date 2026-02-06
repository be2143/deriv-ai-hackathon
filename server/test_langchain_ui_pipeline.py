"""
Test harness for the LangChain UI test spec pipeline using real Panio Mobile App data.

Usage:
  - Ensure OPENAI_API_KEY is set in your environment (e.g. via a .env file or shell).
  - Run:
        python test_langchain_ui_pipeline.py

This script:
  - Constructs a comprehensive UI context for the Panio Mobile App.
  - Uses real extracted requirements from ai_input_processor.
  - Calls run_langchain_ui_test_pipeline to generate a comprehensive test suite.
  - Prints all generated test cases as JSON.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from langchain_ui_test_pipeline import (
    UITestEngineInput,
    run_langchain_ui_test_pipeline,
)
from langchain_openai import ChatOpenAI


def build_mock_ui_context() -> Dict[str, Any]:
    """
    Return a comprehensive mock UI context for the Panio Mobile App.
    
    This includes elements for all major features:
    - Authentication screens
    - Health Marker Dashboard
    - Measurement entry forms
    - Document upload/scanning
    - Charts and visualizations
    - Profile management
    """
    return {
        "page_url": "https://panio.app",
        "title": "Panio - Canine Health Platform",
        "app_type": "React Native Mobile App",
        "elements": [
            # Authentication screens
            {
                "id": "email_input",
                "label": "Email Address",
                "name": "email",
                "data_testid": "login-email-input",
                "css_selector": "input[type='email']",
                "role": "input",
            },
            {
                "id": "password_input",
                "label": "Password",
                "name": "password",
                "data_testid": "login-password-input",
                "css_selector": "input[type='password']",
                "role": "input",
            },
            {
                "id": "login_button",
                "label": "Log In",
                "data_testid": "login-submit-button",
                "css_selector": "button[type='submit']",
                "role": "button",
            },
            {
                "id": "register_link",
                "label": "Create Account",
                "data_testid": "register-link",
                "css_selector": "a[href*='register']",
                "role": "link",
            },
            {
                "id": "forgot_password_link",
                "label": "Forgot Password?",
                "data_testid": "forgot-password-link",
                "css_selector": "a.forgot-password",
                "role": "link",
            },
            
            # Pet selection
            {
                "id": "pet_selector",
                "label": "Select Pet",
                "data_testid": "pet-selector-dropdown",
                "css_selector": "select[name='pet']",
                "role": "select",
            },
            {
                "id": "add_pet_button",
                "label": "Add New Pet",
                "data_testid": "add-pet-button",
                "css_selector": "button.add-pet",
                "role": "button",
            },
            
            # Health Marker Dashboard
            {
                "id": "health_markers_dashboard",
                "label": "Health Markers Dashboard",
                "data_testid": "health-markers-dashboard",
                "css_selector": "div.health-markers-dashboard",
                "role": "container",
            },
            {
                "id": "health_marker_card",
                "label": "Health Marker Card",
                "data_testid": "health-marker-card",
                "css_selector": "div.health-marker-card",
                "role": "card",
            },
            {
                "id": "marker_status_indicator",
                "label": "Status Indicator",
                "data_testid": "marker-status-indicator",
                "css_selector": "span.status-indicator",
                "role": "indicator",
            },
            {
                "id": "view_marker_details_button",
                "label": "View Details",
                "data_testid": "view-marker-details",
                "css_selector": "button.view-details",
                "role": "button",
            },
            {
                "id": "favorite_marker_button",
                "label": "Favorite",
                "data_testid": "favorite-marker",
                "css_selector": "button.favorite",
                "role": "button",
            },
            
            # Measurement Entry Form
            {
                "id": "add_measurement_button",
                "label": "Add Measurement",
                "data_testid": "add-measurement-button",
                "css_selector": "button.add-measurement",
                "role": "button",
            },
            {
                "id": "measurement_modal",
                "label": "Add Health Data Modal",
                "data_testid": "add-health-data-modal",
                "css_selector": "div.modal.add-health-data",
                "role": "modal",
            },
            {
                "id": "marker_name_input",
                "label": "Health Marker",
                "name": "marker_name",
                "data_testid": "marker-name-input",
                "css_selector": "input[name='marker_name']",
                "role": "input",
            },
            {
                "id": "measurement_value_input",
                "label": "Value",
                "name": "value",
                "data_testid": "measurement-value-input",
                "css_selector": "input[name='value']",
                "role": "input",
            },
            {
                "id": "measurement_date_input",
                "label": "Date",
                "name": "date",
                "data_testid": "measurement-date-input",
                "css_selector": "input[type='date']",
                "role": "input",
            },
            {
                "id": "measurement_notes_input",
                "label": "Notes",
                "name": "notes",
                "data_testid": "measurement-notes-input",
                "css_selector": "textarea[name='notes']",
                "role": "textarea",
            },
            {
                "id": "submit_measurement_button",
                "label": "Save Measurement",
                "data_testid": "submit-measurement",
                "css_selector": "button[type='submit'].save-measurement",
                "role": "button",
            },
            {
                "id": "cancel_measurement_button",
                "label": "Cancel",
                "data_testid": "cancel-measurement",
                "css_selector": "button.cancel",
                "role": "button",
            },
            
            # Document Upload/Scanning
            {
                "id": "upload_document_button",
                "label": "Upload Lab Report",
                "data_testid": "upload-document-button",
                "css_selector": "button.upload-document",
                "role": "button",
            },
            {
                "id": "camera_scan_button",
                "label": "Scan Document",
                "data_testid": "camera-scan-button",
                "css_selector": "button.camera-scan",
                "role": "button",
            },
            {
                "id": "file_picker_input",
                "label": "Choose File",
                "name": "file",
                "data_testid": "file-picker-input",
                "css_selector": "input[type='file']",
                "role": "input",
            },
            {
                "id": "camera_scan_modal",
                "label": "Camera Scan Modal",
                "data_testid": "camera-scan-modal",
                "css_selector": "div.modal.camera-scan",
                "role": "modal",
            },
            {
                "id": "capture_button",
                "label": "Capture",
                "data_testid": "capture-button",
                "css_selector": "button.capture",
                "role": "button",
            },
            {
                "id": "document_processing_status",
                "label": "Processing Status",
                "data_testid": "document-processing-status",
                "css_selector": "div.processing-status",
                "role": "status",
            },
            {
                "id": "extracted_measurements_review",
                "label": "Review Extracted Measurements",
                "data_testid": "extracted-measurements-review",
                "css_selector": "div.extracted-measurements",
                "role": "container",
            },
            {
                "id": "edit_extracted_measurement_button",
                "label": "Edit",
                "data_testid": "edit-extracted-measurement",
                "css_selector": "button.edit-measurement",
                "role": "button",
            },
            {
                "id": "confirm_extracted_measurements_button",
                "label": "Confirm",
                "data_testid": "confirm-extracted-measurements",
                "css_selector": "button.confirm-measurements",
                "role": "button",
            },
            
            # Charts and Visualizations
            {
                "id": "measurement_chart",
                "label": "Measurement Chart",
                "data_testid": "measurement-chart",
                "css_selector": "canvas.measurement-chart",
                "role": "chart",
            },
            {
                "id": "chart_type_selector",
                "label": "Chart Type",
                "data_testid": "chart-type-selector",
                "css_selector": "select.chart-type",
                "role": "select",
            },
            {
                "id": "trend_indicator",
                "label": "Trend Indicator",
                "data_testid": "trend-indicator",
                "css_selector": "span.trend-indicator",
                "role": "indicator",
            },
            {
                "id": "health_marker_detail_modal",
                "label": "Health Marker Detail Modal",
                "data_testid": "health-marker-detail-modal",
                "css_selector": "div.modal.health-marker-detail",
                "role": "modal",
            },
            
            # Search and Filter
            {
                "id": "search_input",
                "label": "Search",
                "name": "search",
                "data_testid": "search-input",
                "css_selector": "input[type='search']",
                "role": "input",
            },
            {
                "id": "filter_dropdown",
                "label": "Filter",
                "data_testid": "filter-dropdown",
                "css_selector": "select.filter",
                "role": "select",
            },
            {
                "id": "health_markers_list",
                "label": "Health Markers List",
                "data_testid": "health-markers-list",
                "css_selector": "ul.health-markers-list",
                "role": "list",
            },
            
            # Data Export
            {
                "id": "export_data_button",
                "label": "Export Data",
                "data_testid": "export-data-button",
                "css_selector": "button.export-data",
                "role": "button",
            },
            {
                "id": "export_format_selector",
                "label": "Export Format",
                "data_testid": "export-format-selector",
                "css_selector": "select.export-format",
                "role": "select",
            },
            
            # Profile Management
            {
                "id": "profile_menu_button",
                "label": "Profile Menu",
                "data_testid": "profile-menu-button",
                "css_selector": "button.profile-menu",
                "role": "button",
            },
            {
                "id": "edit_profile_button",
                "label": "Edit Profile",
                "data_testid": "edit-profile-button",
                "css_selector": "button.edit-profile",
                "role": "button",
            },
            {
                "id": "edit_pet_profile_button",
                "label": "Edit Pet Profile",
                "data_testid": "edit-pet-profile-button",
                "css_selector": "button.edit-pet-profile",
                "role": "button",
            },
            {
                "id": "co_parent_management_button",
                "label": "Manage Co-Parents",
                "data_testid": "co-parent-management-button",
                "css_selector": "button.co-parent-management",
                "role": "button",
            },
            {
                "id": "logout_button",
                "label": "Logout",
                "data_testid": "logout-button",
                "css_selector": "button.logout",
                "role": "button",
            },
            
            # QR Code Scanning
            {
                "id": "scan_qr_button",
                "label": "Scan QR Code",
                "data_testid": "scan-qr-button",
                "css_selector": "button.scan-qr",
                "role": "button",
            },
            {
                "id": "qr_scanner_modal",
                "label": "QR Scanner",
                "data_testid": "qr-scanner-modal",
                "css_selector": "div.modal.qr-scanner",
                "role": "modal",
            },
            
            # Error Messages
            {
                "id": "error_message",
                "label": "Error Message",
                "data_testid": "error-message",
                "css_selector": "div.error-message",
                "role": "alert",
            },
            {
                "id": "validation_error",
                "label": "Validation Error",
                "data_testid": "validation-error",
                "css_selector": "span.validation-error",
                "role": "alert",
            },
            {
                "id": "success_message",
                "label": "Success Message",
                "data_testid": "success-message",
                "css_selector": "div.success-message",
                "role": "alert",
            },
        ],
    }


def build_panio_requirements() -> Dict[str, Any]:
    """
    Return the real extracted requirements from ai_input_processor for Panio Mobile App.
    """
    return {
        "overview": "The Panio Mobile App is a user-facing frontend for an AI-driven canine health platform, built with React Native and Expo. It provides comprehensive health tracking, including health marker management, real-time data visualization, AI-powered lab report extraction, and intelligent data entry. The platform is fully implemented and production-ready, offering a complete health management journey for pet owners.",
        "frontend_features": [
            "Main App Shell",
            "Pet Context",
            "Core Data Viewing (Digital Twin, AI Insights, Recommendations)",
            "Interactive Drill-Down & Engagement (Favoriting, detail drill-downs, supplement info)",
            "User Data Input & Lifecycle Management (QR code scanning, medical record uploads)",
            "Profile & Settings Management (User and pet profile editing, co-parent management)",
            "Health Marker Dashboard",
            "Interactive Charts",
            "Manual Entry Form",
            "Document Upload interface",
            "Camera Scanning interface",
            "Data Export functionality",
            "Search & Filter functionality",
            "Trend Analysis views",
            "Authentication screens (Login, Registration, Logout)",
            "HealthMarkerCard (variations for normal, high, low values)",
            "HealthMarkerDetailModal (with charts and measurements)",
            "AddHealthDataModal (for measurement entry)",
            "TrendIndicator components",
            "MeasurementChart (with different chart types)",
            "HealthMarkersList (with filtering and search)",
            "DocumentProcessingStatus (in progress, completed, error states)",
            "ExtractedMeasurementsReview (with editing capabilities)",
            "CameraDocumentCapture (for scanning lab reports)",
            "CameraScanModal (with document guidance)",
            "MedicalRecordUpload (with file picker and camera options)",
            "iOS HealthKit Integration UI",
            "Android Google Fit Integration UI",
            "Quick Settings (Android notification panel)",
        ],
        "functional_requirements": [
            "Manage 50+ health indicators.",
            "Visualize measurement history with interactive charts and trend analysis.",
            "Extract and process measurements from lab reports using AI.",
            "Scan health documents and lab reports using camera OCR.",
            "Input health measurements with auto-completion, validation, and smart suggestions.",
            "View all health indicators with latest values, trends, and status on a dashboard.",
            "Display visual status indicators (Normal, High, Low) with reference ranges.",
            "Track complete historical measurements with filtering and search.",
            "Input measurements via form with validation, auto-completion, quick value shortcuts, notes, and source tracking.",
            "Upload PDF and image lab reports.",
            "Review and edit AI-extracted measurements.",
            "Process measurements in batches.",
            "Capture documents in real-time with preview, image enhancement, and automatic data extraction.",
            "Queue measurements offline and sync when connected.",
            "Export health data as PDF reports or CSV files.",
            "Search and filter specific measurements and health markers.",
            "Identify patterns and changes over time through trend analysis.",
            "Synchronize data live across devices.",
            "Register, login, logout, and manage user sessions securely.",
            "Select and manage pet profiles.",
            "View Digital Twin, AI Insights, and Recommendations.",
            "Favorite items, drill down into details, and view supplement information.",
            "Scan QR codes for kit activation.",
            "Upload medical records.",
            "Edit user and pet profiles.",
            "Manage co-parents.",
            "Display field-specific error messages with suggestions for validation errors.",
            "Display user-friendly messages with retry options for server errors.",
            "Queue operations and sync when online for offline support.",
            "Sync measurements with Apple Health (iOS).",
            "Perform native document scanning with VisionKit (iOS).",
            "Provide tactile feedback for measurement entry (iOS).",
            "Offer Siri shortcuts for quick measurement entry (iOS).",
            "Sync with Google Fit health data (Android).",
            "Utilize ML Kit OCR for advanced text recognition (Android).",
            "Allow adding measurements from the notification panel (Android).",
        ],
        "non_functional_requirements": [
            "Handle thousands of measurements efficiently.",
            "Provide full screen reader support (VoiceOver/TalkBack).",
            "Support keyboard navigation.",
            "Support high contrast modes.",
            "Implement dynamic type scaling for vision accessibility.",
            "Enable voice navigation for hands-free operation.",
            "Ensure smooth scrolling for large measurement lists.",
            "Utilize a health-focused color scheme with status indicators.",
            "Use clear, readable fonts optimized for health data.",
            "Employ medical and health-focused icon set.",
            "Maintain a consistent spacing system for data-dense interfaces.",
            "Provide instant UI feedback with optimistic updates.",
        ],
        "user_flow_context": [
            "Login",
            "Select Pet",
            "View Health Markers",
            "Add Measurements",
            "Upload Lab Reports",
            "Scan Documents",
            "Track Trends",
            "Export Health Data",
            "Sync Offline Changes",
            "Monitor Pet Health",
        ],
    }


def main() -> None:
    """Main test runner."""
    # Ensure API key is available (do not hard-code secrets in this file).
    if "OPENAI_API_KEY" not in os.environ:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Please set it in your environment or .env file "
            "before running this script."
        )

    print("🚀 Testing LangChain UI Test Pipeline with Panio Mobile App")
    print("=" * 70)

    # Build comprehensive UI context
    ui_context = build_mock_ui_context()
    print(f"✅ Built UI context with {len(ui_context['elements'])} elements")

    # Get real extracted requirements
    reqs = build_panio_requirements()
    print(f"✅ Loaded requirements:")
    print(f"   - {len(reqs['functional_requirements'])} functional requirements")
    print(f"   - {len(reqs['non_functional_requirements'])} non-functional requirements")
    print(f"   - {len(reqs['frontend_features'])} frontend features")
    print(f"   - {len(reqs['user_flow_context'])} user flows")

    # Build payload
    payload = UITestEngineInput(
        ui_context=ui_context,
        functional_requirements=reqs["functional_requirements"],
        non_functional_requirements=reqs["non_functional_requirements"],
        user_flow_context=reqs["user_flow_context"],
        overview=reqs["overview"],
        frontend_features=reqs["frontend_features"],
    )

    # OpenAI chat model via LangChain.
    print("\n🤖 Initializing LLM...")
    llm = ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0.0,
    )

    print("🔄 Generating comprehensive test suite...")
    test_specs = run_langchain_ui_test_pipeline(llm, payload)

    print(f"\n{'='*70}")
    print(f"✅ Generated Test Suite: {len(test_specs)} test cases")
    print(f"{'='*70}")

    # Print summary first
    print("\n📋 Test Suite Summary:")
    for idx, test_spec in enumerate(test_specs, 1):
        print(f"  {idx}. {test_spec.test_name}")
        print(f"     {test_spec.description[:80]}...")
        print(f"     Steps: {len(test_spec.steps)}")

    # Print full details
    print(f"\n{'='*70}")
    print("📄 Full Test Case Details:")
    print(f"{'='*70}")
    for idx, test_spec in enumerate(test_specs, 1):
        print(f"\n--- Test Case {idx}/{len(test_specs)}: {test_spec.test_name} ---")
        print(f"Description: {test_spec.description}")
        print(f"Steps ({len(test_spec.steps)}):")
        for step_idx, step in enumerate(test_spec.steps, 1):
            step_str = f"  {step_idx}. {step.action}"
            if step.target:
                step_str += f" target='{step.target}'"
            if step.value:
                step_str += f" value='{step.value}'"
            print(step_str)
        print("\nJSON:")
        print(test_spec.model_dump_json(indent=2, ensure_ascii=False))
        print("-" * 70)


if __name__ == "__main__":
    main()
