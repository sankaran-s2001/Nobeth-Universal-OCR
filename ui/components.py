"""
Reusable visual UI components for Nobeth Universal OCR.
"""

from typing import Optional
from models.schemas import MetricStatus, ReadinessReport, ReadinessStatus


def clean_html(html_str: str) -> str:
    """Strips leading and trailing whitespace per line to avoid markdown code-block triggers."""
    return "\n".join(line.strip() for line in html_str.strip().splitlines() if line.strip())


def render_header(api_key_configured: bool, model_id: str, stage: str) -> str:
    """Renders the top application brand navigation bar."""
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
    else:
        status_html = '<span class="status-badge-chip status-badge-ready"><span class="status-dot-pulse"></span>Ready</span>'

    raw = f"""
<div class="app-header-container animate-entrance">
<div class="brand-identity-wrap">
<div class="brand-logo-icon">
<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="#34D399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M2 17L12 22L22 17" stroke="#38BDF8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M2 12L12 17L22 12" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
</div>
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
<div class="model-tag-chip">{model_id}</div>
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


def render_file_info_chip(filename: str, ext: str, size_str: str, num_pages: int) -> str:
    """Renders the loaded file metadata card."""
    ext_clean = ext.upper().replace(".", "")
    page_text = f"{num_pages} Page" if num_pages == 1 else f"{num_pages} Pages"
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
<span class="status-badge-chip status-badge-ready" style="font-size: 0.7rem; padding: 0.2rem 0.55rem;">Ready for OCR</span>
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


def render_extraction_header(doc_type: str, confidence_level: str, model_id: str) -> str:
    """Renders the AI metadata toolbar above the extraction editors."""
    doc_type_clean = doc_type.replace("_", " ").title()
    conf_class = "status-badge-ready" if confidence_level == "HIGH" else "status-badge-processing" if confidence_level == "MEDIUM" else "status-badge-warning"

    raw = f"""
<div class="meta-chip-toolbar animate-entrance">
<div class="doc-type-label-group">
<span style="font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em;">Inferred Type</span>
<span class="doc-type-pill">{doc_type_clean}</span>
</div>
<div style="display: flex; align-items: center; gap: 0.5rem;">
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
