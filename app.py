"""
Nobeth Universal OCR - Standalone Document Intelligence Workstation
Single-Server Streamlit Application powered by Gemini 3.1 Flash-Lite
"""

import json
import os
import time
from typing import Any, Dict, List, Optional
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
from utils.telemetry import (
    setup_app_logger,
    OperationTimer,
    format_duration,
    generate_operation_id,
    log_operation_banner,
    log_stage_start,
    log_stage_success,
    log_stage_failure,
    log_operation_summary,
)
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
    render_progress_card,
    render_status_banner,
    width_kw,
)
from ui.bulk_workspace import render_bulk_images_workspace, reset_batch_session

# Initialize application logging (idempotent across Streamlit script reruns)
app_logger = setup_app_logger()


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
        "uploader_key": 0,
        "upload_prep_duration": None,
        "stage1_duration": None,
        "stage2_duration": None,
        "export_duration": None,
        "is_extracting": False,
        "is_structuring": False,
        "active_model": get_gemini_model_id(),
        "is_fallback_active": False,
        "app_mode": "📄 Single Document",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session_state()


def reset_session():
    """Resets session state to fresh start for single-document mode."""
    next_uploader_key = st.session_state.get("uploader_key", 0) + 1
    single_doc_keys = [
        "stage", "file_bytes", "filename", "file_ext", "file_size",
        "original_images", "readiness_report", "current_page",
        "raw_text_ai", "raw_text_user", "document_type",
        "confidence_level", "confidence_score", "structured_json_ai",
        "structured_json_user", "is_json_valid", "json_val_msg",
        "error_msg", "success_msg", "active_tab", "upload_prep_duration",
        "stage1_duration", "stage2_duration", "export_duration",
        "is_extracting", "is_structuring",
    ]
    for key in single_doc_keys:
        if key in st.session_state:
            del st.session_state[key]
    init_session_state()
    st.session_state["uploader_key"] = next_uploader_key


# ==============================================================================
# 3. TOP BRAND NAVIGATION & PROGRESS STEPPER
# ==============================================================================
api_key_configured = bool(get_gemini_api_key())
configured_model_id = get_gemini_model_id()
active_display_model = st.session_state.get("active_model", configured_model_id)
is_fallback_model = st.session_state.get("is_fallback_active", False)

# Determine header status stage depending on mode
is_bulk_active = (st.session_state.get("app_mode") == "📚 Bulk Images")
if is_bulk_active:
    if st.session_state.get("batch_is_processing"):
        header_stage = "BULK_PROCESSING"
    elif st.session_state.get("batch_completed"):
        header_stage = "BULK_COMPLETED"
    elif st.session_state.get("batch_preflight"):
        header_stage = "BULK_QUEUED"
    else:
        header_stage = "BULK_EMPTY"
else:
    header_stage = st.session_state.stage

# Render Brand Header with official Nobeth Analytics Logo
st.markdown(
    render_header(api_key_configured, active_display_model, header_stage, is_fallback_model),
    unsafe_allow_html=True,
)

# Application Mode Selector (Single Document vs Bulk Images)
mode_col1, _ = st.columns([1, 1])
with mode_col1:
    app_mode = st.radio(
        "Select Application Mode",
        options=["📄 Single Document", "📚 Bulk Images"],
        horizontal=True,
        label_visibility="collapsed",
        key="app_mode",
    )

is_single_mode = (app_mode == "📄 Single Document")


if is_single_mode:
    # Render Workflow Progression Stepper
    st.markdown(
        render_stepper(st.session_state.stage),
        unsafe_allow_html=True,
    )

    # Global Notification Banners (fixed placeholder ensures root element tree index stability)
    notification_placeholder = st.empty()

    if not api_key_configured:
        notification_placeholder.error(
            "⚠️ **Gemini API Key is not set**. Please configure `GEMINI_API_KEY=your_key_here` in your local `.env` file."
        )
    elif st.session_state.error_msg:
        notification_placeholder.error(f"❌ {st.session_state.error_msg}")
        st.session_state.error_msg = None
    elif st.session_state.success_msg:
        notification_placeholder.success(f"✓ {st.session_state.success_msg}")
        st.session_state.success_msg = None
    else:
        notification_placeholder.empty()


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
            key=f"doc_uploader_{st.session_state.uploader_key}",
        )

        if uploaded_file is not None:
            file_bytes = uploaded_file.getvalue()
            # Detect new upload
            if st.session_state.filename != uploaded_file.name or st.session_state.file_bytes != file_bytes:
                op_id = generate_operation_id("UPL")
                timer = OperationTimer(op_id)
                log_operation_banner(op_id, "DOCUMENT UPLOAD & PREPARATION")

                t_val_start = time.perf_counter()
                log_stage_start(op_id, "FILE VALIDATION", f"{uploaded_file.name} ({len(file_bytes)} bytes)")
                is_valid, err_msg, ext = validate_upload_bytes(uploaded_file.name, file_bytes)
                val_dur = time.perf_counter() - t_val_start

                if not is_valid:
                    log_stage_failure(op_id, "FILE VALIDATION", val_dur, err_msg)
                    log_operation_summary(op_id, False, timer.stop(), err_msg)
                    st.session_state.error_msg = err_msg
                    st.session_state.filename = uploaded_file.name
                    st.session_state.file_bytes = file_bytes
                    st.session_state.original_images = []
                    st.session_state.readiness_report = None
                    st.session_state.raw_text_ai = ""
                    st.session_state.raw_text_user = ""
                    st.session_state.structured_json_ai = None
                    st.session_state.structured_json_user = ""
                    st.session_state.document_type = "unknown"
                    st.session_state.confidence_level = "HIGH"
                    st.session_state.confidence_score = None
                    st.session_state.stage = "EMPTY"
                    st.session_state.upload_prep_duration = None
                else:
                    log_stage_success(op_id, "FILE VALIDATION", val_dur, f"Format: {ext.upper()}")
                    try:
                        report, images = assess_document_readiness(file_bytes, ext, op_id=op_id)
                        total_prep_dur = timer.stop()
                        prep_dur_str = format_duration(total_prep_dur)
                        log_operation_summary(op_id, True, total_prep_dur, f"{len(images)} page(s) ready")

                        st.session_state.upload_prep_duration = prep_dur_str
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
                        fail_dur = timer.stop()
                        log_stage_failure(op_id, "DOCUMENT PREPARATION", fail_dur, str(e))
                        log_operation_summary(op_id, False, fail_dur, str(e))
                        st.session_state.error_msg = f"Failed to process file: {str(e)}"
                        st.session_state.filename = uploaded_file.name
                        st.session_state.file_bytes = file_bytes
                        st.session_state.original_images = []
                        st.session_state.readiness_report = None
                        st.session_state.raw_text_ai = ""
                        st.session_state.raw_text_user = ""
                        st.session_state.structured_json_ai = None
                        st.session_state.structured_json_user = ""
                        st.session_state.stage = "EMPTY"
                        st.session_state.upload_prep_duration = None
        elif st.session_state.filename is not None and st.session_state.stage != "EMPTY":
            reset_session()
            st.rerun()

        # If document is loaded
        if st.session_state.original_images:
            images = st.session_state.original_images
            num_pages = len(images)
            curr_page = st.session_state.current_page
            size_str = format_file_size(st.session_state.file_size)

            # File Metadata Chip (includes measured server prep duration)
            st.markdown(
                render_file_info_chip(
                    filename=st.session_state.filename,
                    ext=st.session_state.file_ext,
                    size_str=size_str,
                    num_pages=num_pages,
                    prep_duration=st.session_state.upload_prep_duration,
                ),
                unsafe_allow_html=True,
            )

            # PDF Page Navigation Toolbar
            if num_pages > 1:
                nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
                with nav_col1:
                    if st.button("◀ Prev", disabled=(curr_page == 0), key="btn_prev_page", **width_kw()):
                        st.session_state.current_page = max(0, curr_page - 1)
                        st.rerun()
                with nav_col2:
                    st.markdown(
                        f"<div style='text-align: center; font-size: 0.82rem; font-weight: 600; color: #94A3B8; padding-top: 0.35rem;'>Page {curr_page + 1} of {num_pages}</div>",
                        unsafe_allow_html=True,
                    )
                with nav_col3:
                    if st.button("Next ▶", disabled=(curr_page >= num_pages - 1), key="btn_next_page", **width_kw()):
                        st.session_state.current_page = min(num_pages - 1, curr_page + 1)
                        st.rerun()

            # Framed Document Preview Stage
            preview_img = images[st.session_state.current_page]
            st.image(
                preview_img,
                caption=f"Document Preview (Page {st.session_state.current_page + 1} of {num_pages})",
                **width_kw(),
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
                extract_placeholder = st.empty()

                if st.session_state.get("is_extracting", False):
                    with extract_placeholder.container():
                        op_id = generate_operation_id("OCR")
                        timer = OperationTimer(op_id)
                        log_operation_banner(op_id, "VISION OCR EXTRACTION")

                        progress_slot = st.empty()
                        total_pages = len(st.session_state.original_images)

                        def on_ocr_progress(stage: str, ratio: Optional[float], meta: Optional[dict]):
                            meta = meta or {}
                            cur_p = meta.get("current_page", 1)
                            tot_p = meta.get("total_pages", total_pages)
                            page_tag = f" (Page {cur_p} of {tot_p})" if tot_p > 1 else ""

                            if stage == "MODEL_SWITCH":
                                new_m = meta.get("new_model", active_display_model)
                                st.session_state.active_model = new_m
                                st.session_state.is_fallback_active = True
                                lbl = "Switching to secondary failover engine (high demand on primary)..."
                            elif stage == "PREPARING":
                                lbl = "Preparing document pages..."
                            elif stage == "PAGE_START":
                                lbl = f"Processing page {cur_p} of {tot_p}..."
                            elif stage == "CALLING_VISION":
                                lbl = f"Waiting for OCR Extraction AI response{page_tag}..."
                            elif stage == "PARSING_RESPONSE":
                                lbl = f"Processing extraction response{page_tag}..."
                            elif stage == "PAGE_COMPLETE":
                                lbl = f"Completed page {cur_p} of {tot_p}..."
                            elif stage == "FINALIZING":
                                lbl = "Finalizing verbatim extracted text..."
                            else:
                                lbl = "Analyzing document with OCR Extraction AI..."

                            progress_slot.markdown(
                                render_progress_card(
                                    title="Stage 1: Vision OCR Extraction",
                                    stage_label=lbl,
                                    progress_ratio=ratio,
                                    elapsed_str=format_duration(timer.elapsed()),
                                    details="Engine: OCR Extraction AI · Zero Domain Assumptions",
                                ),
                                unsafe_allow_html=True,
                            )

                        try:
                            on_ocr_progress("PREPARING", 0.05, {"current_page": 1, "total_pages": total_pages})
                            preprocessed_imgs, _ = preprocess_document_for_vision(
                                st.session_state.original_images,
                                op_id=op_id,
                            )
                            result = extract_raw_document(
                                preprocessed_imgs,
                                progress_callback=on_ocr_progress,
                                op_id=op_id,
                            )
                            total_dur = timer.stop()
                            dur_str = format_duration(total_dur)
                            log_operation_summary(
                                op_id,
                                True,
                                total_dur,
                                f"Model: {result.model_used}, Type: {result.document_type}, Conf: {result.confidence_level.value}",
                            )

                            st.session_state.is_extracting = False
                            st.session_state.stage1_duration = dur_str
                            st.session_state.raw_text_ai = result.verbatim_text
                            st.session_state.raw_text_user = result.verbatim_text
                            st.session_state.document_type = result.document_type
                            st.session_state.confidence_level = result.confidence_level.value
                            st.session_state.confidence_score = result.confidence_score
                            st.session_state.active_model = result.model_used
                            st.session_state.is_fallback_active = (result.model_used != configured_model_id)
                            st.session_state.stage = "RAW_READY"
                            st.session_state.active_tab = "📝 Source-Faithful Raw Extraction"
                            page_str = f"{len(preprocessed_imgs)} page" if len(preprocessed_imgs) == 1 else f"{len(preprocessed_imgs)} pages"
                            st.session_state.success_msg = f"Vision extraction completed in {dur_str} ({page_str} processed)."
                            st.rerun()
                        except Exception as e:
                            st.session_state.is_extracting = False
                            fail_dur = timer.stop()
                            log_stage_failure(op_id, "VISION OCR", fail_dur, str(e))
                            log_operation_summary(op_id, False, fail_dur, str(e))
                            st.session_state.error_msg = f"Extraction error after {format_duration(fail_dur)}: {str(e)}"
                            st.rerun()
                else:
                    if extract_placeholder.button(
                        "🚀 Run OCR Extraction AI ➔",
                        type="primary",
                        key="btn_run_vision_extraction",
                        **width_kw(),
                    ):
                        st.session_state.is_extracting = True
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
                    model_id=st.session_state.get("active_model", configured_model_id),
                    is_fallback=st.session_state.get("is_fallback_active", False),
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

                st.text_area(
                    "Editable Raw Text",
                    height=360,
                    key="raw_text_user",
                    label_visibility="collapsed",
                    disabled=st.session_state.get("is_structuring", False),
                )

                # Action Controls Row
                st.markdown("<div style='margin-top: 0.85rem;'></div>", unsafe_allow_html=True)
                action_placeholder = st.empty()

                def on_reset_raw():
                    st.session_state.raw_text_user = st.session_state.raw_text_ai

                if st.session_state.get("is_structuring", False):
                    with action_placeholder.container():
                        op_id = generate_operation_id("STR")
                        timer = OperationTimer(op_id)
                        log_operation_banner(op_id, "DYNAMIC JSON STRUCTURING")

                        progress_slot = st.empty()

                        def on_struct_progress(stage: str, ratio: Optional[float], meta: Optional[dict]):
                            if stage == "MODEL_SWITCH":
                                new_m = meta.get("new_model", active_display_model)
                                st.session_state.active_model = new_m
                                st.session_state.is_fallback_active = True
                                lbl = "Switching to secondary failover engine (high demand on primary)..."
                            elif stage == "PREPARING_TEXT":
                                lbl = "Preparing reviewed raw document text..."
                            elif stage == "SENDING_PROMPT":
                                lbl = "Waiting for OCR dynamic structuring response..."
                            elif stage == "PARSING_JSON":
                                lbl = "Parsing and validating JSON schema..."
                            elif stage == "EXTRACTING_TRACEABILITY":
                                lbl = "Preparing field traceability results..."
                            elif stage == "COMPLETE":
                                lbl = "Structuring completed successfully..."
                            else:
                                lbl = "Structuring document..."

                            progress_slot.markdown(
                                render_progress_card(
                                    title="Stage 2: Dynamic JSON Structuring",
                                    stage_label=lbl,
                                    progress_ratio=ratio,
                                    elapsed_str=format_duration(timer.elapsed()),
                                    details="Engine: OCR Extraction AI · Zero Hallucination · Preserving Exact Values & Codes",
                                ),
                                unsafe_allow_html=True,
                            )

                        try:
                            on_struct_progress("PREPARING_TEXT", 0.10, {})
                            struct_res = structure_raw_extraction(
                                reviewed_raw_text=st.session_state.raw_text_user,
                                document_type_hint=st.session_state.document_type,
                                progress_callback=on_struct_progress,
                                op_id=op_id,
                            )
                            total_dur = timer.stop()
                            dur_str = format_duration(total_dur)
                            log_operation_summary(
                                op_id,
                                True,
                                total_dur,
                                f"Model: {struct_res.model_used}, Type: {struct_res.document_type}, Valid: {struct_res.is_valid}",
                            )

                            st.session_state.is_structuring = False
                            st.session_state.stage2_duration = dur_str
                            st.session_state.structured_json_ai = struct_res.data
                            formatted_json = json.dumps(struct_res.data, indent=2, ensure_ascii=False)
                            st.session_state.structured_json_user = formatted_json
                            st.session_state.is_json_valid = struct_res.is_valid
                            st.session_state.json_val_msg = struct_res.validation_message
                            st.session_state.active_model = struct_res.model_used
                            st.session_state.is_fallback_active = (struct_res.model_used != configured_model_id)
                            st.session_state.stage = "STRUCTURED_READY"
                            st.session_state.active_tab = "⚡ Dynamic JSON Structure"
                            # Exact wording required by specification
                            st.session_state.success_msg = f"Structuring completed successfully in {dur_str}. Open the ⚡ Dynamic JSON Structure section to review and edit your results."
                            st.rerun()
                        except Exception as e:
                            st.session_state.is_structuring = False
                            fail_dur = timer.stop()
                            log_stage_failure(op_id, "JSON STRUCTURING", fail_dur, str(e))
                            log_operation_summary(op_id, False, fail_dur, str(e))
                            st.session_state.error_msg = f"Structuring error after {format_duration(fail_dur)}: {str(e)}"
                            st.rerun()
                else:
                    with action_placeholder.container():
                        act_col1, act_col2 = st.columns([1, 2], gap="small")
                        with act_col1:
                            st.button("↺ Reset Raw", on_click=on_reset_raw, key="btn_reset_raw", **width_kw())

                        with act_col2:
                            if st.button(
                                "✨ Convert to Dynamic JSON (AI Structuring) ➔",
                                type="primary",
                                key="btn_convert_json",
                                **width_kw(),
                            ):
                                st.session_state.is_structuring = True
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

                    st.text_area(
                        "Editable JSON",
                        height=360,
                        key="structured_json_user",
                        label_visibility="collapsed",
                    )

                    # Re-validate user edit and keep structured_json_ai updated
                    p_data, p_valid, p_err = parse_and_validate_json(st.session_state.structured_json_user)
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
                        t_exp_start = time.perf_counter()
                        exp_op_id = generate_operation_id("EXP")
                        bundle = create_export_bundle(
                            structured_data=st.session_state.structured_json_ai,
                            raw_text=st.session_state.raw_text_user,
                            base_filename=st.session_state.filename or "document",
                            document_type=st.session_state.document_type,
                            confidence=st.session_state.confidence_level,
                            op_id=exp_op_id,
                        )
                        exp_dur = time.perf_counter() - t_exp_start
                        st.session_state.export_duration = format_duration(exp_dur)

                        exp_col1, exp_col2, exp_col3, exp_col4 = st.columns(4, gap="small")
                        with exp_col1:
                            st.download_button(
                                label="⬇ JSON",
                                data=bundle.json_content,
                                file_name=f"{bundle.base_filename}.json",
                                mime="application/json",
                                **width_kw(),
                            )
                        with exp_col2:
                            st.download_button(
                                label="⬇ CSV",
                                data=bundle.csv_content.encode("utf-8-sig"),
                                file_name=f"{bundle.base_filename}.csv",
                                mime="text/csv",
                                **width_kw(),
                            )
                        with exp_col3:
                            st.download_button(
                                label="⬇ TXT",
                                data=bundle.txt_content,
                                file_name=f"{bundle.base_filename}.txt",
                                mime="text/plain",
                                **width_kw(),
                            )
                        with exp_col4:
                            st.button("＋ New", on_click=reset_session, **width_kw())

                        st.markdown(
                            f'<div class="export-timing-note">✓ Export bundle ready in {st.session_state.export_duration} (JSON, CSV, TXT)</div>',
                            unsafe_allow_html=True,
                        )
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

else:
    # ==========================================================================
    # MODE B: BULK IMAGE DOCUMENT INTELLIGENCE WORKSPACE
    # ==========================================================================
    render_bulk_images_workspace(api_key_configured, active_display_model, is_fallback_model)
