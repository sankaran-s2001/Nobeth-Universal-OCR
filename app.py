"""
Nobeth Universal OCR - Standalone Document Intelligence Workstation
Single-Server Streamlit Application powered by Gemini 3.1 Flash-Lite
"""

import json
import os
import streamlit as st
from dotenv import load_dotenv
from PIL import Image

# Load environment
load_dotenv()

from models.schemas import (
    ConfidenceLevel,
    MetricStatus,
    ReadinessStatus,
)
from services.gemini_service import get_gemini_api_key, get_gemini_model_id, GeminiService
from services.preprocessing_service import assess_document_readiness, preprocess_document_for_vision
from services.extraction_service import extract_raw_document
from services.structuring_service import structure_raw_extraction
from services.export_service import create_export_bundle
from utils.file_utils import format_file_size, SUPPORTED_EXTENSIONS
from utils.validation import validate_upload_bytes, parse_and_validate_json
from ui.theme import get_custom_css
from ui.components import (
    render_header,
    render_stepper,
    render_panel_header,
    render_empty_state_left,
    render_empty_state_right,
    render_file_info_chip,
    render_readiness_panel,
    render_extraction_header,
    render_json_validation_badge,
)


# ==============================================================================
# 1. PAGE CONFIGURATION & THEME INJECTION
# ==============================================================================
st.set_page_config(
    page_title="NOBETH Universal OCR",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Inject custom design system CSS
st.markdown(get_custom_css(), unsafe_allow_html=True)


# ==============================================================================
# 2. SESSION STATE MANAGEMENT
# ==============================================================================
def init_session_state():
    defaults = {
        "stage": "EMPTY",  # EMPTY, UPLOADED, RAW_READY, STRUCTURED_READY
        "file_bytes": None,
        "filename": None,
        "file_ext": None,
        "file_size": 0,
        "original_images": [],
        "readiness_report": None,
        "current_page": 0,
        "raw_text_ai": "",
        "raw_text_user": "",
        "document_type": "unknown",
        "confidence_level": "HIGH",
        "confidence_score": None,
        "structured_json_ai": None,
        "structured_json_user": "",
        "is_json_valid": True,
        "json_val_msg": None,
        "error_msg": None,
        "success_msg": None,
        "active_tab": "📝 Source-Faithful Raw Extraction",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session_state()


def reset_session():
    """Resets session state to fresh start."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_session_state()
    st.rerun()


# ==============================================================================
# 3. TOP BRAND NAVIGATION & PROGRESS STEPPER
# ==============================================================================
api_key_configured = bool(get_gemini_api_key())
model_id = get_gemini_model_id()

# Render Brand Header
st.markdown(
    render_header(api_key_configured, model_id, st.session_state.stage),
    unsafe_allow_html=True,
)

# Render Workflow Progression Stepper
st.markdown(
    render_stepper(st.session_state.stage),
    unsafe_allow_html=True,
)

# Global Notification Banners
if not api_key_configured:
    st.error(
        "⚠️ **Gemini API Key is not set**. Please configure `GEMINI_API_KEY=your_key_here` in your local `.env` file."
    )

if st.session_state.error_msg:
    st.error(f"❌ {st.session_state.error_msg}")
    st.session_state.error_msg = None

if st.session_state.success_msg:
    st.success(f"✓ {st.session_state.success_msg}")
    st.session_state.success_msg = None


# ==============================================================================
# 4. WORKSPACE SPLIT LAYOUT (LANDSCAPE-FIRST: 44% / 56%)
# ==============================================================================
col_left, col_right = st.columns([44, 56], gap="large")


# ==============================================================================
# 5. LEFT COLUMN: SOURCE DOCUMENT & DIAGNOSTICS
# ==============================================================================
with col_left:
    st.markdown(
        render_panel_header("document", "SOURCE DOCUMENT"),
        unsafe_allow_html=True,
    )

    # File Uploader
    uploaded_file = st.file_uploader(
        "Upload image or document",
        type=[ext.replace(".", "") for ext in SUPPORTED_EXTENSIONS],
        help="Supported formats: JPG, PNG, WEBP, HEIC, TIFF, PDF",
        label_visibility="collapsed",
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        # Detect new upload
        if st.session_state.filename != uploaded_file.name or st.session_state.file_bytes != file_bytes:
            is_valid, err_msg, ext = validate_upload_bytes(uploaded_file.name, file_bytes)
            if not is_valid:
                st.session_state.error_msg = err_msg
            else:
                try:
                    report, images = assess_document_readiness(file_bytes, ext)
                    st.session_state.file_bytes = file_bytes
                    st.session_state.filename = uploaded_file.name
                    st.session_state.file_ext = ext
                    st.session_state.file_size = len(file_bytes)
                    st.session_state.original_images = images
                    st.session_state.readiness_report = report
                    st.session_state.current_page = 0
                    st.session_state.stage = "UPLOADED"
                    st.session_state.raw_text_ai = ""
                    st.session_state.raw_text_user = ""
                    st.session_state.structured_json_ai = None
                    st.session_state.structured_json_user = ""
                    st.session_state.active_tab = "📝 Source-Faithful Raw Extraction"
                    st.rerun()
                except Exception as e:
                    st.session_state.error_msg = f"Failed to process file: {str(e)}"

    # If document is loaded
    if st.session_state.original_images:
        images = st.session_state.original_images
        num_pages = len(images)
        curr_page = st.session_state.current_page
        size_str = format_file_size(st.session_state.file_size)

        # File Metadata Chip
        st.markdown(
            render_file_info_chip(
                filename=st.session_state.filename,
                ext=st.session_state.file_ext,
                size_str=size_str,
                num_pages=num_pages,
            ),
            unsafe_allow_html=True,
        )

        # PDF Page Navigation Toolbar
        if num_pages > 1:
            nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
            with nav_col1:
                if st.button("◀ Prev", disabled=(curr_page == 0), key="btn_prev_page", use_container_width=True):
                    st.session_state.current_page = max(0, curr_page - 1)
                    st.rerun()
            with nav_col2:
                st.markdown(
                    f"<div style='text-align: center; font-size: 0.82rem; font-weight: 600; color: #94A3B8; padding-top: 0.35rem;'>Page {curr_page + 1} of {num_pages}</div>",
                    unsafe_allow_html=True,
                )
            with nav_col3:
                if st.button("Next ▶", disabled=(curr_page >= num_pages - 1), key="btn_next_page", use_container_width=True):
                    st.session_state.current_page = min(num_pages - 1, curr_page + 1)
                    st.rerun()

        # Framed Document Preview Stage
        preview_img = images[st.session_state.current_page]
        st.image(
            preview_img,
            use_container_width=True,
            caption=f"Document Preview (Page {st.session_state.current_page + 1} of {num_pages})",
        )

        # Document Readiness Diagnostic Panel
        report = st.session_state.readiness_report
        if report:
            st.markdown(
                render_readiness_panel(report),
                unsafe_allow_html=True,
            )

        # Primary Trigger Extraction CTA Button (when uploaded but not yet extracted)
        if st.session_state.stage == "UPLOADED":
            st.markdown("<div style='margin-top: 0.85rem;'></div>", unsafe_allow_html=True)
            if st.button("🚀 Run Gemini Vision Extraction ➔", type="primary", use_container_width=True):
                with st.spinner("Analyzing document with Gemini Vision..."):
                    try:
                        # Non-destructive preprocessing copy
                        preprocessed_imgs, _ = preprocess_document_for_vision(st.session_state.original_images)
                        result = extract_raw_document(preprocessed_imgs)
                        st.session_state.raw_text_ai = result.verbatim_text
                        st.session_state.raw_text_user = result.verbatim_text
                        st.session_state.document_type = result.document_type
                        st.session_state.confidence_level = result.confidence_level.value
                        st.session_state.confidence_score = result.confidence_score
                        st.session_state.stage = "RAW_READY"
                        st.session_state.active_tab = "📝 Source-Faithful Raw Extraction"
                        st.rerun()
                    except Exception as e:
                        st.session_state.error_msg = f"Extraction error: {str(e)}"
                        st.rerun()

    else:
        # Initial Dropzone Empty State
        st.markdown(
            render_empty_state_left(),
            unsafe_allow_html=True,
        )


# ==============================================================================
# 6. RIGHT COLUMN: AI EXTRACTION & STRUCTURED WORKSPACE
# ==============================================================================
with col_right:
    st.markdown(
        render_panel_header("ai", "AI EXTRACTION WORKSPACE"),
        unsafe_allow_html=True,
    )

    if st.session_state.stage in ["RAW_READY", "STRUCTURED_READY"]:
        # AI Metadata Header Bar
        st.markdown(
            render_extraction_header(
                doc_type=st.session_state.document_type,
                confidence_level=st.session_state.confidence_level,
                model_id=model_id,
            ),
            unsafe_allow_html=True,
        )

        # Tabbed Workspace (Custom Horizontal Radio Selector)
        tab_options = [
            "📝 Source-Faithful Raw Extraction",
            "⚡ Dynamic JSON Structure",
        ]
        try:
            active_idx = tab_options.index(st.session_state.active_tab)
        except ValueError:
            active_idx = 0

        selected_tab = st.radio(
            "Workspace Tab Selection",
            options=tab_options,
            index=active_idx,
            horizontal=True,
            label_visibility="collapsed",
            key="workspace_tab_selector",
        )

        if selected_tab != st.session_state.active_tab:
            st.session_state.active_tab = selected_tab
            st.rerun()

        # ----------------------------------------------------------------------
        # TAB 1: RAW EXTRACTION (SOURCE-FAITHFUL)
        # ----------------------------------------------------------------------
        if st.session_state.active_tab == "📝 Source-Faithful Raw Extraction":
            st.markdown(
                '<div style="font-size: 0.76rem; color: var(--text-muted); margin-bottom: 0.5rem; font-weight: 500;">VERBATIM TRANSCRIPTION · PRESERVES EXACT PUNCTUATION, CODES, TABLES & HANDWRITING</div>',
                unsafe_allow_html=True,
            )

            raw_input = st.text_area(
                "Editable Raw Text",
                value=st.session_state.raw_text_user,
                height=360,
                key="raw_text_editor_widget",
                label_visibility="collapsed",
            )

            # Preserve human edits across reruns
            if raw_input != st.session_state.raw_text_user:
                st.session_state.raw_text_user = raw_input

            # Action Controls Row
            st.markdown("<div style='margin-top: 0.85rem;'></div>", unsafe_allow_html=True)
            act_col1, act_col2 = st.columns([1, 2], gap="small")
            with act_col1:
                if st.button("↺ Reset Raw", use_container_width=True):
                    st.session_state.raw_text_user = st.session_state.raw_text_ai
                    st.rerun()

            with act_col2:
                # Trigger Convert to JSON
                if st.button("✨ Convert to Dynamic JSON (AI Structuring) ➔", type="primary", use_container_width=True):
                    with st.spinner("Dynamically understanding and structuring document..."):
                        try:
                            struct_res = structure_raw_extraction(
                                reviewed_raw_text=st.session_state.raw_text_user,
                                document_type_hint=st.session_state.document_type,
                            )
                            st.session_state.structured_json_ai = struct_res.data
                            st.session_state.structured_json_user = json.dumps(struct_res.data, indent=2, ensure_ascii=False)
                            st.session_state.is_json_valid = struct_res.is_valid
                            st.session_state.json_val_msg = struct_res.validation_message
                            st.session_state.stage = "STRUCTURED_READY"
                            st.session_state.active_tab = "⚡ Dynamic JSON Structure"
                            st.rerun()
                        except Exception as e:
                            st.session_state.error_msg = f"Structuring error: {str(e)}"
                            st.rerun()

        # ----------------------------------------------------------------------
        # TAB 2: DYNAMIC STRUCTURED JSON
        # ----------------------------------------------------------------------
        else:
            if st.session_state.structured_json_user:
                # Real-time Syntax Validation
                parsed_dict, is_valid, val_err = parse_and_validate_json(st.session_state.structured_json_user)
                st.markdown(
                    render_json_validation_badge(is_valid, val_err),
                    unsafe_allow_html=True,
                )

                json_input = st.text_area(
                    "Editable JSON",
                    value=st.session_state.structured_json_user,
                    height=360,
                    key="json_editor_widget",
                    label_visibility="collapsed",
                )

                if json_input != st.session_state.structured_json_user:
                    st.session_state.structured_json_user = json_input
                    # Re-validate user edit
                    p_data, p_valid, p_err = parse_and_validate_json(json_input)
                    st.session_state.is_json_valid = p_valid
                    st.session_state.json_val_msg = p_err
                    if p_valid and isinstance(p_data, dict):
                        st.session_state.structured_json_ai = p_data

                # Unified Export Toolbar
                st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                st.markdown(
                    '<div style="font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin-bottom: 0.5rem;">Export Results</div>',
                    unsafe_allow_html=True,
                )

                if st.session_state.is_json_valid and st.session_state.structured_json_ai:
                    bundle = create_export_bundle(
                        structured_data=st.session_state.structured_json_ai,
                        raw_text=st.session_state.raw_text_user,
                        base_filename=st.session_state.filename or "document",
                        document_type=st.session_state.document_type,
                        confidence=st.session_state.confidence_level,
                    )

                    exp_col1, exp_col2, exp_col3, exp_col4 = st.columns(4, gap="small")
                    with exp_col1:
                        st.download_button(
                            label="⬇ JSON",
                            data=bundle.json_content,
                            file_name=f"{bundle.base_filename}.json",
                            mime="application/json",
                            use_container_width=True,
                        )
                    with exp_col2:
                        st.download_button(
                            label="⬇ CSV",
                            data=bundle.csv_content.encode("utf-8-sig"),
                            file_name=f"{bundle.base_filename}.csv",
                            mime="text/csv",
                            use_container_width=True,
                        )
                    with exp_col3:
                        st.download_button(
                            label="⬇ TXT",
                            data=bundle.txt_content,
                            file_name=f"{bundle.base_filename}.txt",
                            mime="text/plain",
                            use_container_width=True,
                        )
                    with exp_col4:
                        if st.button("＋ New", use_container_width=True):
                            reset_session()
                else:
                    st.warning("Please correct syntax errors in the JSON editor above to enable exports.")

            else:
                st.markdown(
                    """
                    <div class="empty-state-card animate-entrance" style="padding: 2.5rem 1rem;">
                        <div class="empty-state-icon-box">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="16 18 22 12 16 6"/>
                                <polyline points="8 6 2 12 8 18"/>
                            </svg>
                        </div>
                        <div class="empty-state-title">Awaiting Structuring Trigger</div>
                        <div class="empty-state-desc">
                            Review your raw extraction in <strong>Tab 1</strong>, then click <strong>Convert to Dynamic JSON</strong> to structure the data.
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    else:
        # Initial Right Column Empty State
        st.markdown(
            render_empty_state_right(),
            unsafe_allow_html=True,
        )
