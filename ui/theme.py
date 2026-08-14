"""
Design system tokens, color palette, and global CSS for Nobeth Universal OCR.
"""

def get_custom_css() -> str:
    """Returns the complete CSS stylesheet for the redesigned interface."""
    return """
<style>
/* ==========================================================================
   1. DESIGN TOKENS & ROOT VARIABLES
   ========================================================================== */
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    /* Background Canvas & Layers */
    --bg-canvas: #05080E;
    --bg-surface-1: rgba(13, 18, 30, 0.85);
    --bg-surface-2: rgba(20, 27, 44, 0.75);
    --bg-surface-3: rgba(28, 38, 60, 0.60);
    --bg-surface-elevated: rgba(24, 33, 54, 0.90);
    --bg-editor: #080C14;

    /* Brand & Accent Palette */
    --brand-emerald: #10B981;
    --brand-emerald-light: #34D399;
    --brand-emerald-dark: #059669;
    --brand-emerald-glow: rgba(16, 185, 129, 0.22);
    --brand-emerald-subtle: rgba(16, 185, 129, 0.10);

    --brand-cyan: #0EA5E9;
    --brand-cyan-light: #38BDF8;
    --brand-cyan-glow: rgba(14, 165, 233, 0.20);
    --brand-cyan-subtle: rgba(14, 165, 233, 0.10);

    /* Status Colors */
    --status-success: #10B981;
    --status-success-bg: rgba(16, 185, 129, 0.12);
    --status-warning: #F59E0B;
    --status-warning-bg: rgba(245, 158, 11, 0.12);
    --status-danger: #EF4444;
    --status-danger-bg: rgba(239, 68, 68, 0.12);

    /* Typography Colors */
    --text-primary: #F8FAFC;
    --text-secondary: #CBD5E1;
    --text-muted: #64748B;
    --text-dim: #475569;

    /* Borders & Outlines */
    --border-subtle: rgba(255, 255, 255, 0.07);
    --border-medium: rgba(255, 255, 255, 0.12);
    --border-strong: rgba(255, 255, 255, 0.20);
    --border-emerald: rgba(16, 185, 129, 0.35);

    /* Shadows & Depth */
    --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.25);
    --shadow-md: 0 8px 24px -4px rgba(0, 0, 0, 0.45);
    --shadow-lg: 0 20px 40px -12px rgba(0, 0, 0, 0.65);
    --shadow-glow: 0 0 25px -5px rgba(16, 185, 129, 0.25);

    /* Border Radii */
    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 14px;
    --radius-xl: 18px;
    --radius-full: 9999px;
}

/* ==========================================================================
   2. GLOBAL RESET & BASE TYPOGRAPHY
   ========================================================================== */
html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: var(--text-primary);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

/* Deep Atmospheric Canvas */
.stApp {
    background-color: var(--bg-canvas) !important;
    background-image: 
        radial-gradient(circle at 10% 0%, rgba(16, 185, 129, 0.08) 0%, transparent 45%),
        radial-gradient(circle at 90% 10%, rgba(14, 165, 233, 0.07) 0%, transparent 45%),
        radial-gradient(circle at 50% 95%, rgba(15, 23, 42, 0.5) 0%, transparent 60%) !important;
    background-attachment: fixed !important;
    background-size: cover !important;
}

/* Streamlit Header & Chrome Clean-up */
header[data-testid="stHeader"] {
    background: transparent !important;
    backdrop-filter: none !important;
    height: 0.5rem !important;
}

div[data-testid="stToolbar"] {
    display: none !important;
}

.block-container {
    padding-top: 1.25rem !important;
    padding-bottom: 2.5rem !important;
    max-width: 1440px !important;
    margin: 0 auto;
}

/* Style Streamlit Columns as Workspace Cards */
div[data-testid="column"] {
    background: var(--bg-surface-1);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xl);
    padding: 1.5rem !important;
    box-shadow: var(--shadow-md);
    min-height: 580px;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

div[data-testid="column"]:hover {
    border-color: var(--border-medium);
}

/* ==========================================================================
   3. BRAND NAVIGATION & TOP APP BAR
   ========================================================================== */
.app-header-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.85rem 1.4rem;
    background: var(--bg-surface-1);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    margin-bottom: 1.1rem;
    box-shadow: var(--shadow-md);
}

.brand-identity-wrap {
    display: flex;
    align-items: center;
    gap: 0.9rem;
}

.brand-logo-icon {
    width: 38px;
    height: 38px;
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.25) 0%, rgba(14, 165, 233, 0.2) 100%);
    border: 1px solid var(--border-emerald);
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 0 16px -2px rgba(16, 185, 129, 0.3);
}

.brand-title-text {
    font-size: 1.3rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    background: linear-gradient(135deg, #FFFFFF 40%, #94A3B8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    line-height: 1.15;
    margin: 0;
}

.brand-badge-pill {
    display: inline-block;
    background: var(--brand-emerald-subtle);
    border: 1px solid var(--border-emerald);
    color: var(--brand-emerald-light);
    font-size: 0.68rem;
    font-weight: 700;
    padding: 0.15rem 0.55rem;
    border-radius: var(--radius-full);
    margin-left: 0.5rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    vertical-align: middle;
}

.brand-tagline-text {
    font-size: 0.78rem;
    color: var(--text-muted);
    font-weight: 400;
    margin: 0;
    letter-spacing: 0.01em;
}

.header-status-wrap {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.status-badge-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.3rem 0.85rem;
    border-radius: var(--radius-full);
    font-size: 0.76rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}

.status-badge-ready {
    background: var(--status-success-bg);
    color: var(--brand-emerald-light);
    border: 1px solid rgba(16, 185, 129, 0.28);
}

.status-badge-processing {
    background: var(--status-warning-bg);
    color: #FCD34D;
    border: 1px solid rgba(245, 158, 11, 0.35);
}

.status-badge-warning {
    background: var(--status-danger-bg);
    color: #FCA5A5;
    border: 1px solid rgba(239, 68, 68, 0.35);
}

.model-tag-chip {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: var(--text-muted);
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid var(--border-subtle);
    padding: 0.25rem 0.65rem;
    border-radius: var(--radius-sm);
}

/* Pulsing Status Dot */
.status-dot-pulse {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background-color: var(--brand-emerald);
    box-shadow: 0 0 8px var(--brand-emerald);
    animation: pulseGlow 2s infinite cubic-bezier(0.4, 0, 0.6, 1);
}

@keyframes pulseGlow {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.45; transform: scale(0.85); }
}

/* ==========================================================================
   4. WORKFLOW STEPPER TIMELINE
   ========================================================================== */
.stepper-timeline-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--bg-surface-1);
    backdrop-filter: blur(16px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 0.75rem 1.4rem;
    margin-bottom: 1.25rem;
    box-shadow: var(--shadow-sm);
    overflow-x: auto;
}

.stepper-node {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--text-dim);
    transition: all 0.25s ease;
    white-space: nowrap;
}

.stepper-num-badge {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.68rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border-subtle);
    color: var(--text-dim);
    transition: all 0.25s ease;
}

/* Node States */
.stepper-node.is-completed {
    color: var(--text-secondary);
}
.stepper-node.is-completed .stepper-num-badge {
    background: var(--brand-emerald-subtle);
    border-color: var(--brand-emerald);
    color: var(--brand-emerald-light);
    box-shadow: 0 0 10px rgba(16, 185, 129, 0.2);
}

.stepper-node.is-active {
    color: #FFFFFF;
    font-weight: 700;
}
.stepper-node.is-active .stepper-num-badge {
    background: linear-gradient(135deg, var(--brand-emerald) 0%, var(--brand-cyan) 100%);
    border-color: #FFFFFF;
    color: #05080E;
    box-shadow: 0 0 14px rgba(16, 185, 129, 0.45);
}

.stepper-connector-line {
    flex: 1;
    height: 2px;
    background: rgba(255, 255, 255, 0.05);
    margin: 0 0.8rem;
    border-radius: 2px;
    min-width: 16px;
}
.stepper-connector-line.is-filled {
    background: linear-gradient(90deg, var(--brand-emerald-light) 0%, rgba(14, 165, 233, 0.4) 100%);
    box-shadow: 0 0 8px rgba(16, 185, 129, 0.2);
}

/* Panel Header */
.panel-header-title {
    font-size: 0.95rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1rem;
    padding-bottom: 0.65rem;
    border-bottom: 1px solid var(--border-subtle);
}

/* ==========================================================================
   5. DROPZONE & SOURCE PREVIEW
   ========================================================================== */
.custom-dropzone-hero {
    border: 1.5px dashed rgba(255, 255, 255, 0.12);
    background: rgba(10, 15, 26, 0.5);
    border-radius: var(--radius-lg);
    padding: 2.2rem 1.25rem;
    text-align: center;
    transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    margin-top: 0.5rem;
    margin-bottom: 0.75rem;
}

.custom-dropzone-hero:hover {
    border-color: var(--border-emerald);
    background: rgba(16, 185, 129, 0.04);
}

.dropzone-icon-circle {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 0.85rem auto;
    color: var(--brand-emerald-light);
}

.dropzone-title-main {
    font-size: 0.94rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 0.25rem;
}

.dropzone-subtitle-muted {
    font-size: 0.76rem;
    color: var(--text-muted);
    margin-bottom: 0.85rem;
}

.format-tags-row {
    display: flex;
    justify-content: center;
    gap: 0.35rem;
    flex-wrap: wrap;
}

.format-tag-pill {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--text-muted);
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-subtle);
    padding: 0.15rem 0.45rem;
    border-radius: var(--radius-sm);
}

/* Document Preview Image Scaling to Align Height with Workstation */
div[data-testid="stImage"] {
    background: rgba(10, 15, 26, 0.45) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: 0.6rem !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    max-height: 400px !important;
    overflow: hidden !important;
    margin-top: 0.5rem !important;
    margin-bottom: 0.85rem !important;
}

div[data-testid="stImage"] img {
    max-height: 380px !important;
    object-fit: contain !important;
    width: auto !important;
    height: auto !important;
    border-radius: var(--radius-sm) !important;
}

/* Custom Styled Radio Tabs (for workspace tab selector) */
div[data-testid="stRadioGroup"] {
    flex-direction: row !important;
    background-color: rgba(10, 15, 26, 0.6) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: 0.25rem !important;
    gap: 0.35rem !important;
    margin-bottom: 0.85rem !important;
}

div[data-testid="stRadioGroup"] > div {
    margin: 0 !important;
    padding: 0 !important;
}

/* Target each radio label option container */
div[data-testid="stRadioGroup"] [data-baseweb="radio"] {
    background-color: transparent !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    padding: 0.4rem 1.1rem !important;
    margin-right: 0px !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    display: flex !important;
    align-items: center !important;
}

/* Hide the default radio circle indicator */
div[data-testid="stRadioGroup"] [data-baseweb="radio"] div:first-child {
    display: none !important;
}

/* Custom styles for radio labels */
div[data-testid="stRadioGroup"] [data-baseweb="radio"] span {
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    font-family: inherit !important;
}

/* Hover state for tabs */
div[data-testid="stRadioGroup"] [data-baseweb="radio"]:hover {
    background: rgba(255, 255, 255, 0.04) !important;
}

/* Style selected option */
div[data-testid="stRadioGroup"] [data-baseweb="radio"][aria-checked="true"] {
    background: rgba(255, 255, 255, 0.08) !important;
    border: 1px solid var(--border-subtle) !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
}

div[data-testid="stRadioGroup"] [data-baseweb="radio"][aria-checked="true"] span {
    color: #FFFFFF !important;
}

/* File Info Header Chip */
.file-info-chip-card {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--bg-surface-2);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 0.65rem 0.9rem;
    margin-bottom: 0.85rem;
}

.file-name-text {
    font-size: 0.86rem;
    font-weight: 600;
    color: var(--text-primary);
    max-width: 240px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.file-meta-subtext {
    font-size: 0.72rem;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
}

/* ==========================================================================
   6. DOCUMENT READINESS DIAGNOSTIC PANEL
   ========================================================================== */
.readiness-panel-container {
    background: var(--bg-surface-2);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 0.95rem;
    margin-top: 0.85rem;
    margin-bottom: 0.85rem;
}

.readiness-header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
}

.readiness-title-label {
    font-size: 0.76rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
}

.readiness-grid-6col {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.45rem;
}

.diag-metric-cell {
    background: rgba(10, 15, 26, 0.75);
    border: 1px solid rgba(255, 255, 255, 0.04);
    border-radius: var(--radius-sm);
    padding: 0.45rem 0.6rem;
    transition: all 0.2s ease;
}
.diag-metric-cell:hover {
    border-color: var(--border-medium);
}

.diag-name-text {
    font-size: 0.65rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
}

.diag-value-text {
    font-size: 0.78rem;
    font-weight: 700;
    margin-top: 0.15rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.val-good { color: var(--brand-emerald-light); }
.val-adequate { color: var(--brand-cyan-light); }
.val-warning { color: var(--status-warning); }
.val-poor { color: var(--status-danger); }

/* ==========================================================================
   7. AI EXTRACTION & STRUCTURED WORKSPACE
   ========================================================================== */
.meta-chip-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--bg-surface-2);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 0.6rem 0.9rem;
    margin-bottom: 0.85rem;
}

.doc-type-label-group {
    display: flex;
    align-items: center;
    gap: 0.6rem;
}

.doc-type-pill {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(14, 165, 233, 0.12) 100%);
    border: 1px solid var(--border-emerald);
    color: #FFFFFF;
    font-size: 0.82rem;
    font-weight: 700;
    padding: 0.2rem 0.65rem;
    border-radius: var(--radius-sm);
    letter-spacing: 0.02em;
}

/* Custom Styled Tabs */
.stTabs [data-baseweb="tab-list"] {
    background-color: rgba(10, 15, 26, 0.6) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: 0.25rem !important;
    gap: 0.35rem !important;
    margin-bottom: 0.85rem !important;
}

.stTabs [data-baseweb="tab"] {
    height: 36px !important;
    border-radius: var(--radius-sm) !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    background-color: transparent !important;
    border: none !important;
    padding: 0.4rem 1rem !important;
    transition: all 0.2s ease !important;
}

.stTabs [aria-selected="true"] {
    background: rgba(255, 255, 255, 0.08) !important;
    color: #FFFFFF !important;
    border: 1px solid var(--border-subtle) !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
}

/* Editor Surface & Monospace Customization */
div[data-testid="stTextArea"] textarea {
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    font-size: 0.82rem !important;
    line-height: 1.6 !important;
    background-color: var(--bg-editor) !important;
    color: #E2E8F0 !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: 0.85rem !important;
    box-shadow: inset 0 2px 6px rgba(0, 0, 0, 0.4) !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

div[data-testid="stTextArea"] textarea:focus {
    border-color: var(--border-emerald) !important;
    box-shadow: 0 0 0 1px var(--brand-emerald), inset 0 2px 6px rgba(0, 0, 0, 0.4) !important;
}

/* ==========================================================================
   8. BUTTON DESIGN SYSTEM
   ========================================================================== */
/* Primary Action Buttons (Glowing Emerald) */
div.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #10B981 0%, #059669 100%) !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    font-size: 0.84rem !important;
    letter-spacing: 0.02em !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    border-radius: var(--radius-md) !important;
    padding: 0.55rem 1.25rem !important;
    box-shadow: 0 4px 16px -2px rgba(16, 185, 129, 0.4) !important;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
}

div.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #34D399 0%, #10B981 100%) !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 24px -2px rgba(16, 185, 129, 0.55) !important;
}

div.stButton > button[kind="primary"]:active {
    transform: translateY(0) scale(0.98) !important;
}

/* Secondary & Standard Buttons */
div.stButton > button[kind="secondary"], 
div.stButton > button:not([kind="primary"]) {
    background: rgba(20, 27, 44, 0.75) !important;
    color: var(--text-secondary) !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: 0.5rem 1rem !important;
    transition: all 0.2s ease !important;
}

div.stButton > button[kind="secondary"]:hover,
div.stButton > button:not([kind="primary"]):hover {
    background: rgba(30, 41, 64, 0.9) !important;
    color: #FFFFFF !important;
    border-color: var(--border-medium) !important;
    transform: translateY(-1px) !important;
}

/* Download Buttons (Export Toolbar) */
div[data-testid="stDownloadButton"] > button {
    background: rgba(16, 24, 40, 0.85) !important;
    color: var(--text-primary) !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: 0.5rem 0.85rem !important;
    transition: all 0.2s ease !important;
    width: 100% !important;
}

div[data-testid="stDownloadButton"] > button:hover {
    background: rgba(16, 185, 129, 0.12) !important;
    border-color: var(--border-emerald) !important;
    color: var(--brand-emerald-light) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.15) !important;
}

/* ==========================================================================
   9. EMPTY STATES & AMBIENT GRAPHICS
   ========================================================================== */
.empty-state-card {
    text-align: center;
    padding: 3.5rem 1.5rem;
    color: var(--text-muted);
}

.empty-state-icon-box {
    width: 64px;
    height: 64px;
    margin: 0 auto 1.25rem auto;
    border-radius: 50%;
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(14, 165, 233, 0.06) 100%);
    border: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: var(--shadow-sm);
}

.empty-state-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 0.4rem;
}

.empty-state-desc {
    font-size: 0.82rem;
    color: var(--text-muted);
    max-width: 320px;
    margin: 0 auto;
    line-height: 1.5;
}

/* Alerts / Banners */
div[data-testid="stAlert"] {
    background: rgba(15, 23, 42, 0.85) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    font-size: 0.82rem !important;
}

/* Animations */
@keyframes fadeInSlideUp {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

.animate-entrance {
    animation: fadeInSlideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
</style>
"""
