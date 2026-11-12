"""
Reusable visual UI components for Nobeth Universal OCR.
"""

import base64
import inspect
import os
from typing import Optional
import streamlit as st
from models.schemas import MetricStatus, ReadinessReport, ReadinessStatus

_OFFICIAL_LOGO_BASE64: Optional[str] = None


def get_nobeth_logo_base64() -> Optional[str]:
    """Retrieves and caches the base64 data URI of the official Nobeth Analytics logo."""
    global _OFFICIAL_LOGO_BASE64
    if _OFFICIAL_LOGO_BASE64 is not None:
        return _OFFICIAL_LOGO_BASE64

    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "assets", "nobeth-analytics.png"),
        os.path.join("static", "assets", "nobeth-analytics.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    _OFFICIAL_LOGO_BASE64 = base64.b64encode(f.read()).decode("utf-8")
                    return _OFFICIAL_LOGO_BASE64
            except Exception:
                pass
    return None


def clean_html(html_str: str) -> str:
    """Strips leading and trailing whitespace per line to avoid markdown code-block triggers."""
    return "\n".join(line.strip() for line in html_str.strip().splitlines() if line.strip())


def render_header(api_key_configured: bool, model_id: str, stage: str, is_fallback: bool = False) -> str:
    """Renders the top application brand navigation bar with the official Nobeth Analytics logo."""
    if not api_key_configured:
        status_html = '<span class="status-badge-chip status-badge-warning">● API Key Missing</span>'
    elif stage == "EMPTY":
        status_html = '<span class="status-badge-chip status-badge-ready"><span class="status-dot-pulse"></span>Engine Ready</span>'
    elif stage == "UPLOADED":
        status_html = '<span class="status-badge-chip status-badge-processing"><span class="status-dot-pulse" style="background:#F59E0B; box-shadow:0 0 8px #F59E0B;"></span>Document Loaded</span>'
    elif stage == "RAW_READY":
        status_html = '<span class="status-badge-chip status-badge-ready"><span class="status-dot-pulse"></span>Raw Extracted</span>'
    elif stage == "STRUCTURED_READY":
        status_html = '<span class="status-badge-chip status-badge-ready"><span class="status-dot-pulse"></span>Structured & Ready</span>'
    elif stage == "BULK_EMPTY":
        status_html = '<span class="status-badge-chip status-badge-ready"><span class="status-dot-pulse"></span>Bulk Engine Ready</span>'
    elif stage == "BULK_QUEUED":
        status_html = '<span class="status-badge-chip status-badge-processing"><span class="status-dot-pulse" style="background:#0EA5E9; box-shadow:0 0 8px #0EA5E9;"></span>Batch Queued</span>'
    elif stage == "BULK_PROCESSING":
        status_html = '<span class="status-badge-chip status-badge-processing"><span class="status-dot-pulse" style="background:#F59E0B; box-shadow:0 0 8px #F59E0B;"></span>Processing Queue...</span>'
    elif stage == "BULK_COMPLETED":
        status_html = '<span class="status-badge-chip status-badge-ready"><span class="status-dot-pulse"></span>Batch Complete</span>'
    else:
        status_html = '<span class="status-badge-chip status-badge-ready"><span class="status-dot-pulse"></span>Ready</span>'

    if is_fallback:
        model_tag_html = f'<div class="model-tag-chip" style="border-color: rgba(56, 189, 248, 0.45); color: #38BDF8; background: rgba(14, 165, 233, 0.12);" title="Auto-failover model active">⚡ {model_id} (fallback)</div>'
    else:
        model_tag_html = f'<div class="model-tag-chip">{model_id}</div>'

    logo_b64 = get_nobeth_logo_base64()
    if logo_b64:
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" alt="Nobeth Analytics" class="nobeth-official-logo" />'
    else:
        logo_html = """<div class="brand-logo-icon">
<svg width="36" height="36" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="#34D399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M2 17L12 22L22 17" stroke="#38BDF8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M2 12L12 17L22 12" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
</div>"""

    raw = f"""
<div class="app-header-container animate-entrance">
<div class="brand-identity-wrap">
{logo_html}
<div>
<div style="display: flex; align-items: center;">
<span class="brand-title-text">NOBETH</span>
<span class="brand-badge-pill">Universal OCR</span>
</div>
<div class="brand-tagline-text">Source-Faithful Document Intelligence & Dynamic Structured Understanding</div>
</div>
</div>
<div class="header-status-wrap">
{status_html}
{model_tag_html}
</div>
</div>
"""
    return clean_html(raw)


def render_stepper(stage: str) -> str:
    """Renders the horizontal workflow progression stepper."""
    steps = [
        {"num": "01", "label": "Upload"},
        {"num": "02", "label": "Preprocess"},
        {"num": "03", "label": "Vision OCR"},
        {"num": "04", "label": "Review Raw"},
        {"num": "05", "label": "Structuring"},
        {"num": "06", "label": "Multi-Export"},
    ]

    # Map current application stage to step progress indices (0 to 5)
    if stage == "EMPTY":
        active_idx = 0
        completed_idx = -1
    elif stage == "UPLOADED":
        active_idx = 2
        completed_idx = 1
    elif stage == "RAW_READY":
        active_idx = 4
        completed_idx = 3
    elif stage == "STRUCTURED_READY":
        active_idx = 5
        completed_idx = 5
    else:
        active_idx = 0
        completed_idx = -1

    nodes_html = []
    for i, s in enumerate(steps):
        is_completed = i <= completed_idx and (stage == "STRUCTURED_READY" or i < active_idx)
        is_active = i == active_idx and not (stage == "STRUCTURED_READY" and i < 5)

        state_class = "is-completed" if is_completed else "is-active" if is_active else ""
        badge_content = "✓" if is_completed else s["num"]

        node_markup = f'<div class="stepper-node {state_class}"><div class="stepper-num-badge">{badge_content}</div><span>{s["label"]}</span></div>'
        nodes_html.append(node_markup)

        if i < len(steps) - 1:
            line_class = "is-filled" if i < completed_idx or (i == completed_idx and is_completed) else ""
            nodes_html.append(f'<div class="stepper-connector-line {line_class}"></div>')

    raw = f'<div class="stepper-timeline-bar animate-entrance">{"".join(nodes_html)}</div>'
    return clean_html(raw)


def render_panel_header(icon_type: str, title: str) -> str:
    """Renders a panel header bar with clean SVG icon."""
    if icon_type == "document":
        icon_svg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#34D399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>'
    else:
        icon_svg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'

    raw = f"""
<div class="panel-header-title">
{icon_svg}
<span>{title}</span>
</div>
"""
    return clean_html(raw)


def render_empty_state_left() -> str:
    """Renders the upload area placeholder."""
    raw = """
<div class="custom-dropzone-hero animate-entrance">
<div class="dropzone-icon-circle">
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
<polyline points="17 8 12 3 7 8"/>
<line x1="12" y1="3" x2="12" y2="15"/>
</svg>
</div>
<div class="dropzone-title-main">Drop your document or image here</div>
<div class="dropzone-subtitle-muted">Universal OCR engine with zero hardcoded domain constraints</div>
<div class="format-tags-row">
<span class="format-tag-pill">JPG</span>
<span class="format-tag-pill">PNG</span>
<span class="format-tag-pill">WEBP</span>
<span class="format-tag-pill">HEIC</span>
<span class="format-tag-pill">TIFF</span>
<span class="format-tag-pill">PDF</span>
</div>
</div>
"""
    return clean_html(raw)


def render_empty_state_right() -> str:
    """Renders the AI extraction workspace placeholder."""
    raw = """
<div class="empty-state-card animate-entrance">
<div class="empty-state-icon-box">
<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#34D399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
<circle cx="12" cy="12" r="10"/>
<line x1="12" y1="16" x2="12" y2="12"/>
<line x1="12" y1="8" x2="12.01" y2="8"/>
</svg>
</div>
<div class="empty-state-title">AI Workstation Ready</div>
<div class="empty-state-desc">
Upload a document on the left and launch <strong>Gemini Vision Extraction</strong> to generate source-faithful data and dynamic JSON structures.
</div>
</div>
"""
    return clean_html(raw)


def render_file_info_chip(filename: str, ext: str, size_str: str, num_pages: int, prep_duration: Optional[str] = None) -> str:
    """Renders the loaded file metadata card with optional measured preparation duration."""
    ext_clean = ext.upper().replace(".", "")
    page_text = f"{num_pages} Page" if num_pages == 1 else f"{num_pages} Pages"
    status_label = f"Ready for OCR · {prep_duration}" if prep_duration else "Ready for OCR"
    raw = f"""
<div class="file-info-chip-card animate-entrance">
<div style="display: flex; align-items: center; gap: 0.65rem;">
<div style="color: #34D399;">
<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
<polyline points="14 2 14 8 20 8"/>
<line x1="16" y1="13" x2="8" y2="13"/>
<line x1="16" y1="17" x2="8" y2="17"/>
<polyline points="10 9 9 9 8 9"/>
</svg>
</div>
<div>
<div class="file-name-text" title="{filename}">{filename}</div>
<div class="file-meta-subtext">{ext_clean} · {size_str} · {page_text}</div>
</div>
</div>
<span class="status-badge-chip status-badge-ready" style="font-size: 0.7rem; padding: 0.2rem 0.55rem;">{status_label}</span>
</div>
"""
    return clean_html(raw)


def render_readiness_panel(report: ReadinessReport) -> str:
    """Renders the diagnostic readiness metrics grid."""
    status_class = "status-badge-ready" if report.overall_status == ReadinessStatus.READY else "status-badge-processing" if report.overall_status == ReadinessStatus.READY_WITH_WARNINGS else "status-badge-warning"

    def _val_class(m_status: MetricStatus) -> str:
        if m_status == MetricStatus.GOOD:
            return "val-good"
        elif m_status == MetricStatus.ADEQUATE:
            return "val-adequate"
        elif m_status == MetricStatus.WARNING:
            return "val-warning"
        return "val-poor"

    warnings_html = ""
    if report.warnings:
        warn_items = "".join([f"<li style='margin-bottom:0.2rem;'>{w}</li>" for w in report.warnings])
        warnings_html = f"""
<div style="margin-top: 0.65rem; padding-top: 0.5rem; border-top: 1px solid var(--border-subtle); font-size: 0.72rem; color: var(--status-warning);">
<ul style="margin: 0; padding-left: 1.1rem;">{warn_items}</ul>
</div>
"""

    raw = f"""
<div class="readiness-panel-container animate-entrance">
<div class="readiness-header-row">
<span class="readiness-title-label">Document Readiness Diagnostic</span>
<span class="status-badge-chip {status_class}">{report.overall_status.value} · {report.readiness_score:.0f}%</span>
</div>
<div class="readiness-grid-6col">
<div class="diag-metric-cell">
<div class="diag-name-text">Resolution</div>
<div class="diag-value-text {_val_class(report.resolution.status)}">{report.resolution.value_display}</div>
</div>
<div class="diag-metric-cell">
<div class="diag-name-text">Blur</div>
<div class="diag-value-text {_val_class(report.blur.status)}">{report.blur.value_display}</div>
</div>
<div class="diag-metric-cell">
<div class="diag-name-text">Contrast</div>
<div class="diag-value-text {_val_class(report.contrast.status)}">{report.contrast.value_display}</div>
</div>
<div class="diag-metric-cell">
<div class="diag-name-text">Brightness</div>
<div class="diag-value-text {_val_class(report.brightness.status)}">{report.brightness.value_display}</div>
</div>
<div class="diag-metric-cell">
<div class="diag-name-text">Skew</div>
<div class="diag-value-text {_val_class(report.skew.status)}">{report.skew.value_display}</div>
</div>
<div class="diag-metric-cell">
<div class="diag-name-text">Readability</div>
<div class="diag-value-text {_val_class(report.readability.status)}">{report.readability.value_display}</div>
</div>
</div>
{warnings_html}
</div>
"""
    return clean_html(raw)


def render_extraction_header(doc_type: str, confidence_level: str, model_id: str, is_fallback: bool = False) -> str:
    """Renders the AI metadata toolbar above the extraction editors."""
    doc_type_clean = doc_type.replace("_", " ").title()
    conf_class = "status-badge-ready" if confidence_level == "HIGH" else "status-badge-processing" if confidence_level == "MEDIUM" else "status-badge-warning"

    if is_fallback:
        model_badge = f'<span class="model-tag-chip" style="border-color: rgba(56, 189, 248, 0.45); color: #38BDF8; background: rgba(14, 165, 233, 0.12);" title="Auto-failover model active">⚡ {model_id}</span>'
    else:
        model_badge = f'<span class="model-tag-chip">{model_id}</span>'

    raw = f"""
<div class="meta-chip-toolbar animate-entrance">
<div class="doc-type-label-group">
<span style="font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em;">Inferred Type</span>
<span class="doc-type-pill">{doc_type_clean}</span>
</div>
<div style="display: flex; align-items: center; gap: 0.5rem;">
{model_badge}
<span class="status-badge-chip {conf_class}">Confidence: {confidence_level}</span>
</div>
</div>
"""
    return clean_html(raw)


def render_json_validation_badge(is_valid: bool, val_msg: Optional[str] = None) -> str:
    """Renders the live validation pill above the JSON editor."""
    if is_valid:
        msg = val_msg or "Valid JSON Schema"
        raw = f'<div style="font-size: 0.78rem; font-weight: 600; color: var(--brand-emerald-light); margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.35rem;"><span style="font-size: 0.9rem;">✓</span> {msg}</div>'
    else:
        msg = val_msg or "Syntax Error"
        raw = f'<div style="font-size: 0.78rem; font-weight: 600; color: var(--status-danger); margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.35rem;"><span style="font-size: 0.9rem;">⚠</span> {msg}</div>'
    return clean_html(raw)


def render_progress_card(
    title: str,
    stage_label: str,
    progress_ratio: Optional[float] = None,
    elapsed_str: Optional[str] = None,
    details: Optional[str] = None,
) -> str:
    """
    Renders an interactive animated progress card with real-time stage description,
    smooth keyframe-animated progress bar, and real-time live seconds countdown timer.
    """
    is_active = (progress_ratio is None or progress_ratio < 1.0)

    if is_active:
        card_class = "progress-panel-card is-streaming animate-entrance"
        bar_class = "progress-bar-fill active-streaming"
        width_style = ""
        timing_html = '<span class="timing-badge-chip">⏱ <span class="nobeth-live-countdown"></span> <span style="opacity: 0.65; font-size: 0.66rem; font-weight: 500;">remaining</span></span>'
    else:
        card_class = "progress-panel-card animate-entrance"
        bar_class = "progress-bar-fill completed-bar"
        width_style = "width: 100%;"
        timing_label = elapsed_str or "100%"
        timing_html = f'<span class="timing-badge-chip">⏱ {timing_label}</span>'

    details_html = f'<div style="font-size: 0.72rem; color: #64748B; margin-top: 0.35rem;">{details}</div>' if details else ""
    bar_style_attr = f'style="{width_style}"' if width_style else ""

    raw = f"""
<div class="{card_class}">
  <div class="progress-header-row">
    <div class="progress-title-text">
      <span class="progress-spinner-ring"></span>
      <span>{title}</span>
    </div>
    {timing_html}
  </div>
  <div class="progress-stage-desc">
    <span style="color: #34D399;">●</span>
    <span>{stage_label}</span>
  </div>
  <div class="progress-bar-track">
    <div class="{bar_class}" {bar_style_attr}></div>
  </div>
  {details_html}
</div>
"""
    return clean_html(raw)


def render_status_banner(
    message: str,
    is_error: bool = False,
    duration_str: Optional[str] = None,
) -> str:
    """Renders a structured, visually aligned success or error notification banner."""
    status_class = "status-feedback-error" if is_error else "status-feedback-success"
    icon = "❌" if is_error else "✓"
    timing_html = f'<span class="timing-badge-chip">⏱ {duration_str}</span>' if duration_str else ""

    raw = f"""
<div class="status-feedback-banner {status_class} animate-entrance">
  <div style="display: flex; align-items: center; gap: 0.6rem;">
    <span>{icon}</span>
    <span>{message}</span>
  </div>
  {timing_html}
</div>
"""
    return clean_html(raw)


def render_batch_summary_card(
    total_selected: int,
    valid_count: int,
    unsupported_count: int,
    invalid_count: int,
    total_size_str: str,
) -> str:
    """Renders the initial pre-flight batch summary card before processing starts."""
    raw = f"""
<div class="batch-summary-card animate-entrance">
  <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 0.75rem;">
    <div>
      <span style="font-size: 0.95rem; font-weight: 700; color: #F8FAFC;">📚 Batch Upload Summary</span>
      <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 0.15rem;">Review file readiness before initiating sequential execution</div>
    </div>
    <span class="status-badge-chip status-badge-ready" style="font-size: 0.75rem;">Sequential Pipeline</span>
  </div>
  <div class="batch-stats-grid">
    <div class="batch-stat-box">
      <div class="batch-stat-val" style="color: #38BDF8;">{total_selected}</div>
      <div class="batch-stat-label">Total Files</div>
    </div>
    <div class="batch-stat-box">
      <div class="batch-stat-val" style="color: #34D399;">{valid_count}</div>
      <div class="batch-stat-label">Valid Images</div>
    </div>
    <div class="batch-stat-box">
      <div class="batch-stat-val" style="color: #F59E0B;">{unsupported_count}</div>
      <div class="batch-stat-label">Unsupported</div>
    </div>
    <div class="batch-stat-box">
      <div class="batch-stat-val" style="color: #EF4444;">{invalid_count}</div>
      <div class="batch-stat-label">Invalid</div>
    </div>
    <div class="batch-stat-box">
      <div class="batch-stat-val" style="font-size: 1.1rem; color: #CBD5E1;">{total_size_str}</div>
      <div class="batch-stat-label">Total Size</div>
    </div>
  </div>
</div>
"""
    return clean_html(raw)


def render_batch_dashboard_metrics(
    total: int,
    completed: int,
    successful: int,
    partial: int,
    failed: int,
    skipped: int,
    elapsed_str: str,
    avg_str: str,
    eta_str: str,
) -> str:
    """Renders real-time live batch processing metrics cards."""
    remaining = max(0, total - completed)
    raw = f"""
<div class="batch-stats-grid animate-entrance" style="margin-top: 0.25rem;">
  <div class="batch-stat-box">
    <div class="batch-stat-val" style="color: #F8FAFC;">{completed}/{total}</div>
    <div class="batch-stat-label">Progress</div>
  </div>
  <div class="batch-stat-box">
    <div class="batch-stat-val" style="color: #34D399;">{successful}</div>
    <div class="batch-stat-label">Successful</div>
  </div>
  <div class="batch-stat-box">
    <div class="batch-stat-val" style="color: #38BDF8;">{partial}</div>
    <div class="batch-stat-label">Partial</div>
  </div>
  <div class="batch-stat-box">
    <div class="batch-stat-val" style="color: #EF4444;">{failed}</div>
    <div class="batch-stat-label">Failed</div>
  </div>
  <div class="batch-stat-box">
    <div class="batch-stat-val" style="color: #94A3B8;">{remaining}</div>
    <div class="batch-stat-label">Remaining</div>
  </div>
  <div class="batch-stat-box">
    <div class="batch-stat-val" style="font-size: 1.1rem; color: #F59E0B;">{elapsed_str}</div>
    <div class="batch-stat-label">Elapsed</div>
  </div>
  <div class="batch-stat-box">
    <div class="batch-stat-val" style="font-size: 1.1rem; color: #CBD5E1;">{avg_str}</div>
    <div class="batch-stat-label">Avg / Image</div>
  </div>
  <div class="batch-stat-box">
    <div class="batch-stat-val" style="font-size: 1.1rem; color: #38BDF8;">{eta_str}</div>
    <div class="batch-stat-label">Est. Remaining</div>
  </div>
</div>
"""
    return clean_html(raw)


def render_batch_current_file(
    file_num: int,
    total: int,
    filename: str,
    stage_label: str,
    model_name: Optional[str] = None,
) -> str:
    """Renders the banner highlighting the file actively being processed."""
    model_chip = f'<span class="model-tag-chip" style="font-size: 0.68rem; padding: 2px 7px;">⚡ {model_name}</span>' if model_name else ""
    raw = f"""
<div class="batch-current-file-box animate-entrance">
  <div class="batch-file-title">
    <span class="status-dot-pulse" style="background: #38BDF8; box-shadow: 0 0 8px #38BDF8;"></span>
    <span>Processing image {file_num} of {total}: <strong style="color: #38BDF8;">{filename}</strong></span>
  </div>
  <div style="display: flex; align-items: center; gap: 0.5rem;">
    {model_chip}
    <span class="batch-stage-chip">{stage_label}</span>
  </div>
</div>
"""
    return clean_html(raw)


def render_batch_completion_summary(
    total: int,
    successful: int,
    partial: int,
    failed: int,
    skipped: int,
    duration_str: str,
    zip_filename: str,
) -> str:
    """Renders the final completion summary card for a finished batch."""
    is_flawless = (failed == 0 and partial == 0 and skipped == 0)
    badge_class = "status-badge-ready" if is_flawless else "status-badge-processing"
    badge_text = "✓ 100% Successful" if is_flawless else "Batch Completed"

    raw = f"""
<div class="batch-summary-card animate-entrance" style="border-color: rgba(16, 185, 129, 0.45); background: rgba(13, 18, 30, 0.95);">
  <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 0.75rem;">
    <div>
      <span style="font-size: 1.05rem; font-weight: 700; color: #F8FAFC;">🎉 Batch Processing Completed</span>
      <div style="font-size: 0.78rem; color: #94A3B8; margin-top: 0.2rem;">Total execution duration: <strong style="color: #34D399;">{duration_str}</strong></div>
    </div>
    <span class="status-badge-chip {badge_class}" style="font-size: 0.78rem;">{badge_text}</span>
  </div>
  <div class="batch-stats-grid">
    <div class="batch-stat-box">
      <div class="batch-stat-val" style="color: #F8FAFC;">{total}</div>
      <div class="batch-stat-label">Total Files</div>
    </div>
    <div class="batch-stat-box">
      <div class="batch-stat-val" style="color: #34D399;">{successful}</div>
      <div class="batch-stat-label">Successful</div>
    </div>
    <div class="batch-stat-box">
      <div class="batch-stat-val" style="color: #38BDF8;">{partial}</div>
      <div class="batch-stat-label">Partial</div>
    </div>
    <div class="batch-stat-box">
      <div class="batch-stat-val" style="color: #EF4444;">{failed}</div>
      <div class="batch-stat-label">Failed</div>
    </div>
    <div class="batch-stat-box">
      <div class="batch-stat-val" style="color: #94A3B8;">{skipped}</div>
      <div class="batch-stat-label">Skipped</div>
    </div>
  </div>
  <div style="font-size: 0.78rem; color: #94A3B8; margin-top: 0.85rem; display: flex; align-items: center; gap: 0.4rem;">
    <span>📦 Archive ready:</span>
    <span style="font-family: 'JetBrains Mono', monospace; color: #38BDF8;">{zip_filename}</span>
  </div>
</div>
"""
    return clean_html(raw)


def style_batch_table(df):
    """
    Applies consistent status-based visual row styling across live and completed batch tables.
    - SUCCESS: subtle grey/slate background for completed tracking
    - SUCCESS_REVIEWED: subtle grey/slate with human-review indication
    - PROCESSING: distinct soft cyan/teal highlight
    - RETRYING: distinct soft blue/indigo highlight
    - FAILED / INVALID: soft red background
    - PARTIAL: soft amber background
    - QUEUED / VALID: normal dark background with muted text
    - SKIPPED / UNSUPPORTED: muted neutral background
    """
    def _row_style(row):
        status = str(row.get("Status", "")).upper()
        if status in ["SUCCESS", "COMPLETED"]:
            style = "background-color: rgba(255, 255, 255, 0.06); color: #E2E8F0;"
        elif status == "SUCCESS_REVIEWED":
            style = "background-color: rgba(56, 189, 248, 0.08); color: #E0F2FE; font-weight: 500;"
        elif status == "PROCESSING":
            style = "background-color: rgba(14, 165, 233, 0.22); color: #38BDF8; font-weight: 600;"
        elif status == "RETRYING":
            style = "background-color: rgba(99, 102, 241, 0.22); color: #A5B4FC; font-weight: 600;"
        elif status in ["FAILED", "INVALID"]:
            style = "background-color: rgba(239, 68, 68, 0.18); color: #FCA5A5; font-weight: 500;"
        elif status == "PARTIAL":
            style = "background-color: rgba(245, 158, 11, 0.18); color: #FCD34D; font-weight: 500;"
        elif status in ["SKIPPED", "UNSUPPORTED"]:
            style = "background-color: rgba(100, 116, 139, 0.10); color: #94A3B8;"
        else:
            style = "background-color: transparent; color: #94A3B8;"
        return [style] * len(row)

    if hasattr(df, "style"):
        return df.style.apply(_row_style, axis=1)
    return df


def width_kw(is_stretch: bool = True) -> dict:
    """Returns width='stretch' if supported by current Streamlit, else use_container_width=True."""
    params = inspect.signature(st.button).parameters
    if "width" in params:
        return {"width": "stretch" if is_stretch else "content"}
    return {"use_container_width": is_stretch}
