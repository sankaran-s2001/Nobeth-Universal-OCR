"""
Bulk Image Processing Workspace: UI controller for multi-image selection, folder uploads,
live sequential dashboard, individual downloads, stage-aware retry, human review, and complete batch ZIP archive export.
"""

import os
import time
from typing import Any, Dict, List, Optional
import pandas as pd
from PIL import Image
import streamlit as st

from models.batch_schemas import (
    BatchItemResult,
    BatchItemStage,
    BatchItemStatus,
    BatchJobSummary,
    BatchPreflightSummary,
)
from services.batch_processing_service import (
    IMAGE_EXTENSIONS,
    MAX_BATCH_FILES_DEFAULT,
    MAX_SINGLE_FILE_BYTES_DEFAULT,
    MAX_TOTAL_BATCH_BYTES_DEFAULT,
    is_item_retryable,
    process_batch_sequential,
    restructure_single_batch_item,
    retry_all_failed_batch_items,
    retry_single_batch_item,
    validate_batch_preflight,
)
from services.gemini_service import GeminiService
from ui.components import (
    render_batch_completion_summary,
    render_batch_current_file,
    render_batch_dashboard_metrics,
    render_batch_summary_card,
    render_panel_header,
    style_batch_table,
    width_kw,
)
from utils.file_utils import format_file_size
from utils.telemetry import format_duration


def _on_reset_bulk_raw_text(widget_key: str, reset_text: str):
    """Safely resets the bulk raw editor text in session state prior to widget instantiation."""
    st.session_state[widget_key] = reset_text


def reset_batch_session():
    """Resets bulk batch processing session state."""
    st.session_state["batch_preflight"] = None
    st.session_state["batch_summary"] = None
    st.session_state["batch_results"] = []
    st.session_state["batch_source_bytes"] = {}
    st.session_state["batch_is_processing"] = False
    st.session_state["batch_completed"] = False
    st.session_state["batch_uploader_key"] = st.session_state.get("batch_uploader_key", 0) + 1


def render_bulk_images_workspace(api_key_configured: bool, active_model_id: str, is_fallback_model: bool):
    """
    Renders the complete Bulk Image Document Intelligence workspace.
    Supports Multiple Image Selection, Folder Uploads, Live Table Tracking,
    Stage-Aware Retry of Failed Images, and Human-in-the-Loop Editable OCR Re-Structuring.
    """
    if "batch_uploader_key" not in st.session_state:
        st.session_state["batch_uploader_key"] = 0
    if "batch_preflight" not in st.session_state:
        st.session_state["batch_preflight"] = None
    if "batch_summary" not in st.session_state:
        st.session_state["batch_summary"] = None
    if "batch_results" not in st.session_state:
        st.session_state["batch_results"] = []
    if "batch_source_bytes" not in st.session_state:
        st.session_state["batch_source_bytes"] = {}
    if "batch_is_processing" not in st.session_state:
        st.session_state["batch_is_processing"] = False
    if "batch_completed" not in st.session_state:
        st.session_state["batch_completed"] = False

    st.markdown(
        render_panel_header("batch", "BULK DOCUMENT INTELLIGENCE"),
        unsafe_allow_html=True,
    )

    if not api_key_configured:
        st.error("⚠️ **Gemini API Key is not set**. Please configure `GEMINI_API_KEY=your_key_here` in your local `.env` file to process images.")
        return

    # 1. COMPLETED BATCH VIEW
    if st.session_state.batch_completed and st.session_state.batch_summary is not None:
        summary: BatchJobSummary = st.session_state.batch_summary
        results: List[BatchItemResult] = st.session_state.batch_results
        bytes_map: Dict[int, bytes] = st.session_state.get("batch_source_bytes", {})

        # Completion summary header
        st.markdown(
            render_batch_completion_summary(
                total=summary.total_files,
                successful=summary.success_count,
                partial=summary.partial_count,
                failed=summary.failed_count,
                skipped=summary.skipped_count,
                duration_str=format_duration(summary.total_duration),
                zip_filename=summary.zip_filename or "Batch_Archive.zip",
            ),
            unsafe_allow_html=True,
        )

        # Check for eligible retry items
        eligible_retry_items = [
            r for r in results
            if is_item_retryable(r)[0] and r.file_index in bytes_map
        ]

        # Action Buttons Row: Download ZIP, Retry All Failed (if any), Start New Batch
        if eligible_retry_items:
            c_zip, c_retry_all, c_new = st.columns([2.2, 1.6, 1], gap="medium")
        else:
            c_zip, c_new = st.columns([3, 1], gap="medium")
            c_retry_all = None

        with c_zip:
            if summary.zip_archive_path and os.path.exists(summary.zip_archive_path):
                try:
                    with open(summary.zip_archive_path, "rb") as zf:
                        zip_bytes = zf.read()
                    st.download_button(
                        label=f"⬇️ Download Complete Batch ZIP ({format_file_size(len(zip_bytes))})",
                        data=zip_bytes,
                        file_name=summary.zip_filename,
                        mime="application/zip",
                        type="primary",
                        key="btn_dl_batch_zip",
                        **width_kw(),
                    )
                except Exception as e:
                    st.error(f"Failed to read archive: {e}")
            else:
                st.warning("Archive file could not be located on disk.")

        if c_retry_all is not None:
            with c_retry_all:
                if st.button(
                    f"🔁 Retry All Failed Images ({len(eligible_retry_items)})",
                    type="secondary",
                    key="btn_retry_all_failed",
                    help="Sequentially re-runs only eligible failed images without reprocessing successful items.",
                    **width_kw(),
                ):
                    with st.status(f"Retrying {len(eligible_retry_items)} failed image(s) sequentially...", expanded=True) as status_box:
                        def on_global_retry_start(step_i, total_i, fname):
                            status_box.update(label=f"Retrying image {step_i} of {total_i}: {fname}...")

                        retry_all_failed_batch_items(
                            summary=summary,
                            results=results,
                            file_bytes_map=bytes_map,
                            gemini_service=GeminiService(),
                            on_retry_start=on_global_retry_start,
                        )
                        status_box.update(label="All eligible failed images retried! Batch ZIP updated.", state="complete")
                    st.rerun()

        with c_new:
            st.button("＋ Start New Batch", on_click=reset_batch_session, key="btn_new_batch_top", **width_kw())

        st.markdown("---")

        # Tabular Batch Overview with consistent status row highlighting
        st.markdown("#### 📋 Processed Images Overview")
        df_records = []
        for r in results:
            df_records.append({
                "No.": f"{r.file_index:02d}",
                "Filename": r.original_filename,
                "Status": r.status.value,
                "Document Type": r.document_type,
                "Engine": "OCR Extraction AI" if r.model_used else "-",
                "OCR Time": format_duration(r.ocr_duration) if r.ocr_duration else "-",
                "Structuring Time": format_duration(r.structuring_duration) if r.structuring_duration else "-",
                "Total Time": format_duration(r.total_duration) if r.total_duration else "-",
            })
        st.dataframe(style_batch_table(pd.DataFrame(df_records)), hide_index=True, **width_kw())

        st.markdown("#### 📂 Individual Results & Downloads")
        for item in results:
            idx_str = f"{item.file_index:02d}"
            status_emoji = "✓" if item.is_success else ("⚠️" if item.status == BatchItemStatus.PARTIAL else "❌")
            expander_title = f"{status_emoji} [{idx_str}/{summary.total_files:02d}] {item.original_filename} — {item.status.value} ({format_duration(item.total_duration or 0.0)})"

            with st.expander(expander_title, expanded=(item.file_index == 1 or item.status == BatchItemStatus.FAILED)):
                if item.is_success:
                    col_info, col_dls = st.columns([1, 1], gap="medium")
                    with col_info:
                        st.markdown(f"**Document Type:** `{item.document_type}` | **Confidence:** `{item.confidence}`")
                        st.markdown(f"**Engine:** `OCR Extraction AI` | **Quality Score:** `{item.readiness_score or 0.0:.0f}%`")
                        if item.is_reviewed:
                            st.markdown(f"**Review Status:** `✓ Human-Reviewed` (Revision `{item.review_count}` | {item.last_modified_at or 'updated'})")
                        st.markdown(f"**Timings:** OCR: `{format_duration(item.ocr_duration or 0.0)}` | Structuring: `{format_duration(item.structuring_duration or 0.0)}` | Total: `{format_duration(item.total_duration or 0.0)}`")

                    with col_dls:
                        st.markdown("**Download Individual Formats:**")
                        d1, d2, d3 = st.columns(3)
                        with d1:
                            if item.json_content:
                                st.download_button(
                                    label="⬇ JSON",
                                    data=item.json_content,
                                    file_name=item.json_filename or f"{item.original_filename}.json",
                                    mime="application/json",
                                    key=f"dl_json_{item.file_index}",
                                    **width_kw(),
                                )
                        with d2:
                            if item.csv_content:
                                st.download_button(
                                    label="⬇ CSV",
                                    data=item.csv_content.encode("utf-8-sig"),
                                    file_name=item.csv_filename or f"{item.original_filename}.csv",
                                    mime="text/csv",
                                    key=f"dl_csv_{item.file_index}",
                                    **width_kw(),
                                )
                        with d3:
                            if item.txt_content:
                                st.download_button(
                                    label="⬇ TXT",
                                    data=item.txt_content,
                                    file_name=item.txt_filename or f"{item.original_filename}.txt",
                                    mime="text/plain",
                                    key=f"dl_txt_{item.file_index}",
                                    **width_kw(),
                                )

                    # Previews: Structured Data & Editable Raw OCR Text
                    tab_json, tab_raw = st.tabs(["Structured Data Preview", "Verbatim Raw OCR Text"])
                    with tab_json:
                        if item.structured_data:
                            st.json(item.structured_data)
                    with tab_raw:
                        widget_key = f"bulk_raw_editor_{item.file_index}_{summary.batch_id}"
                        if widget_key not in st.session_state:
                            st.session_state[widget_key] = item.reviewed_raw_text or item.raw_text or ""

                        st.markdown(f"**Verbatim OCR Text Editor** (Source: `{item.original_filename}`)")
                        if item.is_reviewed:
                            st.caption(f"✓ Human-Reviewed (Revision {item.review_count} — Last updated: {item.last_modified_at or 'recently'})")

                        edited_text = st.text_area(
                            label="Edit OCR extracted text:",
                            height=220,
                            key=widget_key,
                            help="Correct any misspelled words or numbers, then click 'Re-Structure JSON with AI'.",
                        )

                        c_rst, c_restruct = st.columns([1, 2], gap="small")
                        with c_rst:
                            st.button(
                                "↺ Reset to Original OCR Text",
                                key=f"btn_rst_{item.file_index}_{summary.batch_id}",
                                on_click=_on_reset_bulk_raw_text,
                                args=(widget_key, item.original_raw_text or item.raw_text or ""),
                                **width_kw(),
                            )
                        with c_restruct:
                            if st.button("✨ Re-Structure JSON with AI", type="primary", key=f"btn_restr_{item.file_index}_{summary.batch_id}", **width_kw()):
                                current_raw = (st.session_state.get(widget_key) or edited_text or "").strip()
                                if not current_raw:
                                    st.error("Cannot re-structure: raw text is empty.")
                                else:
                                    with st.spinner("Re-Structuring dynamic JSON with AI (Stage 2 only)..."):
                                        try:
                                            restructure_single_batch_item(
                                                item_index=item.file_index,
                                                summary=summary,
                                                results=results,
                                                reviewed_text=current_raw,
                                                gemini_service=GeminiService(),
                                            )
                                            st.success("Re-structuring completed successfully! Results & ZIP updated.")
                                            time.sleep(0.5)
                                            st.rerun()
                                        except Exception as restr_err:
                                            st.error(f"Re-structuring failed: {restr_err}")

                elif item.status == BatchItemStatus.PARTIAL:
                    st.warning(f"**Partial Extraction:** Stage 1 Verbatim OCR succeeded, but Stage 2 Dynamic Structuring failed: {item.error_message}")
                    if item.txt_content:
                        st.download_button(
                            label=f"⬇ Download Verbatim TXT ({item.txt_filename})",
                            data=item.txt_content,
                            file_name=item.txt_filename,
                            mime="text/plain",
                            key=f"dl_txt_partial_{item.file_index}",
                            **width_kw(),
                        )

                    widget_key = f"bulk_raw_editor_{item.file_index}_{summary.batch_id}"
                    if widget_key not in st.session_state:
                        st.session_state[widget_key] = item.reviewed_raw_text or item.raw_text or ""

                    edited_text = st.text_area(
                        label="Stage 1 Preserved Raw Text (Editable):",
                        height=180,
                        key=widget_key,
                    )

                    c_ret_p, c_rst_p, c_restr_p = st.columns([1, 1, 1], gap="small")
                    with c_ret_p:
                        f_bytes = bytes_map.get(item.file_index)
                        if f_bytes and st.button("🔁 Retry Structuring", key=f"btn_retry_partial_{item.file_index}_{summary.batch_id}", **width_kw()):
                            with st.spinner("Retrying Stage 2 Structuring..."):
                                retry_single_batch_item(
                                    item_index=item.file_index,
                                    summary=summary,
                                    results=results,
                                    file_bytes=f_bytes,
                                    gemini_service=GeminiService(),
                                )
                            st.rerun()

                    with c_rst_p:
                        st.button(
                            "↺ Reset Raw",
                            key=f"btn_rst_part_{item.file_index}_{summary.batch_id}",
                            on_click=_on_reset_bulk_raw_text,
                            args=(widget_key, item.original_raw_text or item.raw_text or ""),
                            **width_kw(),
                        )

                    with c_restr_p:
                        if st.button("✨ Re-Structure JSON with AI", type="primary", key=f"btn_restr_part_{item.file_index}_{summary.batch_id}", **width_kw()):
                            current_raw = (st.session_state.get(widget_key) or edited_text or "").strip()
                            if not current_raw:
                                st.error("Cannot re-structure: text is empty.")
                            else:
                                with st.spinner("Structuring JSON with AI..."):
                                    try:
                                        restructure_single_batch_item(
                                            item_index=item.file_index,
                                            summary=summary,
                                            results=results,
                                            reviewed_text=current_raw,
                                            gemini_service=GeminiService(),
                                        )
                                        st.rerun()
                                    except Exception as err:
                                        st.error(f"Structuring failed: {err}")

                else:
                    # FAILED or INVALID
                    st.error(f"**Failure in stage:** `{item.failed_stage or 'UNKNOWN'}` | **Category:** `{item.error_category or 'GENERAL_ERROR'}`")
                    display_err = item.error_message or "An error occurred during processing."
                    if "[object Object]" in str(display_err):
                        display_err = "Gemini returned an unparseable response. The document may be blank, illegible, or blocked by content safety filters."
                    st.code(display_err)

                    is_ret, ret_reason = is_item_retryable(item)
                    f_bytes = bytes_map.get(item.file_index)
                    if is_ret and f_bytes:
                        if st.button("🔁 Retry This Image", type="primary", key=f"btn_retry_single_{item.file_index}_{summary.batch_id}", **width_kw()):
                            with st.spinner(f"Retrying {item.original_filename}..."):
                                retry_single_batch_item(
                                    item_index=item.file_index,
                                    summary=summary,
                                    results=results,
                                    file_bytes=f_bytes,
                                    gemini_service=GeminiService(),
                                )
                            st.rerun()
                    else:
                        st.info(f"ℹ️ {ret_reason}")

                    if item.retry_history:
                        with st.expander(f"Retry History ({len(item.retry_history)} attempt(s))"):
                            for h in item.retry_history:
                                st.markdown(f"- **Attempt {h.get('attempt')}:** `{h.get('timestamp')}` | Stage: `{h.get('failed_stage')}` | Error: `{h.get('error_message')}`")

        return

    # 2. SELECTION & UPLOAD VIEW
    c_mode1, c_mode2 = st.columns([1, 2])
    with c_mode1:
        upload_mode = st.radio(
            "Upload Source",
            options=["📁 Multiple Images", "📂 Select Folder"],
            horizontal=True,
            key="bulk_upload_source_choice",
        )

    uploader_key = st.session_state.batch_uploader_key

    if upload_mode == "📁 Multiple Images":
        uploaded_files = st.file_uploader(
            "Select multiple image files",
            type=[ext.replace(".", "") for ext in IMAGE_EXTENSIONS],
            accept_multiple_files=True,
            help="Hold Ctrl or Shift to select multiple JPG, PNG, WEBP, HEIC, or TIFF images.",
            key=f"uploader_multi_{uploader_key}",
        )
    else:
        uploaded_files = st.file_uploader(
            "Select an entire folder of images",
            accept_multiple_files="directory",
            help="Uploads all images inside the selected directory and supported nested folders.",
            key=f"uploader_dir_{uploader_key}",
        )

    if not uploaded_files:
        st.markdown(
            """
            <div class="empty-state-card animate-entrance" style="padding: 2.75rem 1.5rem; text-align: center; margin-top: 1rem;">
                <div class="empty-state-icon-box">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                        <line x1="8" y1="21" x2="16" y2="21"/>
                        <line x1="12" y1="17" x2="12" y2="21"/>
                    </svg>
                </div>
                <div class="empty-state-title">Bulk Image Document Intelligence</div>
                <div class="empty-state-desc">
                    Select <strong>Multiple Images</strong> or upload an entire <strong>Folder</strong> above.<br/>
                    All documents will be processed sequentially through OCR Extraction AI & Dynamic JSON Structuring.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # Run Pre-flight Validation
    preflight: BatchPreflightSummary = validate_batch_preflight(uploaded_files)
    st.session_state.batch_preflight = preflight

    # Display Preflight Summary Card
    st.markdown(
        render_batch_summary_card(
            total_selected=preflight.total_selected,
            valid_count=preflight.valid_count,
            unsupported_count=preflight.unsupported_count,
            invalid_count=preflight.invalid_count,
            total_size_str=preflight.total_upload_size_str,
        ),
        unsafe_allow_html=True,
    )

    if preflight.error_message:
        st.error(f"⚠️ {preflight.error_message}")
        if not preflight.is_processable:
            st.button("🔄 Clear & Try Again", on_click=reset_batch_session, key="btn_clear_unproc")
            return

    # Start Batch Trigger & Clear Controls
    c_run, c_clr = st.columns([3, 1], gap="medium")
    with c_run:
        start_clicked = st.button(
            f"🚀 Start Batch Processing ({preflight.valid_count} Valid Images)",
            type="primary",
            key="btn_run_batch",
            disabled=(not preflight.is_processable),
            **width_kw(),
        )
    with c_clr:
        st.button("🔄 Clear Uploads", on_click=reset_batch_session, key="btn_clear_uploads", **width_kw())

    # 3. SEQUENTIAL PROCESSING EXECUTION
    if start_clicked:
        st.session_state.batch_is_processing = True

        # Cache source image bytes in session state for stage-aware retries
        source_bytes_map = {}
        for idx, f in enumerate(uploaded_files, start=1):
            if hasattr(f, "getvalue"):
                b = f.getvalue()
            elif hasattr(f, "read"):
                b = f.read()
                if hasattr(f, "seek"):
                    f.seek(0)
            elif isinstance(f, bytes):
                b = f
            else:
                b = b""
            source_bytes_map[idx] = b
        st.session_state["batch_source_bytes"] = source_bytes_map

        st.markdown("---")
        st.markdown("### ⚡ Live Batch Processing Dashboard")

        dashboard_container = st.empty()
        progress_bar = st.progress(0.0)
        current_file_container = st.empty()
        table_container = st.empty()

        # Build initial status rows for live dataframe
        live_table_rows = []
        for p_item in preflight.items:
            live_table_rows.append({
                "No.": f"{len(live_table_rows)+1:02d}",
                "Filename": p_item.filename,
                "Status": p_item.status.value,
                "Current Stage": "QUEUED" if p_item.status == BatchItemStatus.VALID else p_item.status.value,
                "OCR Time": "-",
                "Structuring Time": "-",
                "Total Time": "-",
            })

        table_container.dataframe(style_batch_table(pd.DataFrame(live_table_rows)), hide_index=True, **width_kw())

        t_start_live = time.perf_counter()

        def on_item_start_live(idx: int, total: int, fname: str):
            current_file_container.markdown(
                render_batch_current_file(idx, total, fname, "STARTING", active_model_id),
                unsafe_allow_html=True,
            )

        def on_stage_change_live(idx: int, total: int, fname: str, stage: BatchItemStage):
            frac = min(1.0, max(0.0, (idx - 1) / total))
            progress_bar.progress(frac)
            current_file_container.markdown(
                render_batch_current_file(idx, total, fname, stage.value, active_model_id),
                unsafe_allow_html=True,
            )
            if idx <= len(live_table_rows):
                live_table_rows[idx - 1]["Current Stage"] = stage.value
                live_table_rows[idx - 1]["Status"] = "PROCESSING"
                table_container.dataframe(style_batch_table(pd.DataFrame(live_table_rows)), hide_index=True, **width_kw())

        def on_item_complete_live(idx: int, total: int, res: BatchItemResult):
            frac = min(1.0, max(0.0, idx / total))
            progress_bar.progress(frac)

            elapsed = time.perf_counter() - t_start_live
            avg_per_item = elapsed / idx if idx > 0 else 0.0
            remaining = total - idx
            est_rem = avg_per_item * remaining
            eta_str = format_duration(est_rem) if idx >= 2 and remaining > 0 else "Estimating..."

            # Update row in live table
            if idx <= len(live_table_rows):
                live_table_rows[idx - 1]["Status"] = res.status.value
                live_table_rows[idx - 1]["Current Stage"] = res.current_stage.value
                live_table_rows[idx - 1]["OCR Time"] = format_duration(res.ocr_duration) if res.ocr_duration else "-"
                live_table_rows[idx - 1]["Structuring Time"] = format_duration(res.structuring_duration) if res.structuring_duration else "-"
                live_table_rows[idx - 1]["Total Time"] = format_duration(res.total_duration) if res.total_duration else "-"
                table_container.dataframe(style_batch_table(pd.DataFrame(live_table_rows)), hide_index=True, **width_kw())

            # Update metrics dashboard
            dashboard_container.markdown(
                render_batch_dashboard_metrics(
                    total=total,
                    completed=idx,
                    successful=sum(1 for r in live_table_rows[:idx] if r["Status"] in ["SUCCESS", "SUCCESS_REVIEWED"]),
                    partial=sum(1 for r in live_table_rows[:idx] if r["Status"] == "PARTIAL"),
                    failed=sum(1 for r in live_table_rows[:idx] if r["Status"] in ["FAILED", "INVALID"]),
                    skipped=sum(1 for r in live_table_rows[:idx] if r["Status"] in ["SKIPPED", "UNSUPPORTED"]),
                    elapsed_str=format_duration(elapsed),
                    avg_str=format_duration(avg_per_item),
                    eta_str=eta_str,
                ),
                unsafe_allow_html=True,
            )

        gemini_service = GeminiService()

        # Run sequential queue
        summary, results = process_batch_sequential(
            uploaded_files=uploaded_files,
            gemini_service=gemini_service,
            preflight=preflight,
            on_item_start=on_item_start_live,
            on_stage_change=on_stage_change_live,
            on_item_complete=on_item_complete_live,
        )

        st.session_state.batch_summary = summary
        st.session_state.batch_results = results
        st.session_state.batch_is_processing = False
        st.session_state.batch_completed = True

        st.rerun()
