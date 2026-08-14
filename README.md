# Nobeth Universal OCR

> **Extract. Understand. Structure.**  
> A standalone, single-server document intelligence application powered by **Google Gemini 3.1 Flash-Lite** and **Streamlit**.

---

## 🌟 Overview

**Nobeth Universal OCR** is a minimal, high-accuracy document intelligence workspace designed to extract and structure information from almost any image or document format without rigid domain assumptions.

Unlike traditional OCR systems that force documents into hardcoded schemas (e.g. liquor receipts or regional invoice formats), Nobeth Universal OCR operates on a **universal two-stage architecture**:

1. **Stage 1 (Raw Extraction)**: Gemini Vision inspects the source document directly and extracts visible text, tables, codes, and handwriting with verbatim fidelity.
2. **Stage 2 (Dynamic Structuring)**: Gemini dynamically determines the appropriate JSON schema for that specific document (e.g. invoice, receipt, ID card, medical form, table, handwritten note).

---

## 📐 Architecture & Workflow

```
                             USER
                              │
                              ▼
                     STREAMLIT UI (Single Server)
                              │
                              ▼
                       FILE VALIDATION
                (Format, Magic Bytes, Size Limit)
                              │
                              ▼
               LIGHTWEIGHT PREPROCESSING & READINESS
             (Laplacian Blur, RMS Contrast, Luminance,
             Skew Detection; Original Bytes Untouched)
                              │
                              ▼
               GEMINI VISION PRIMARY EXTRACTION
                    (gemini-3.1-flash-lite)
                              │
                              ▼
                RAW SOURCE-FAITHFUL EXTRACTION
              (Verbatim, Exact Wording, Tables,
            Leading Zeros, Uncertainties Preserved)
                              │
                              ▼
                     HUMAN REVIEW / EDIT
                     (Raw Text Editor)
                              │
                              ▼
                      [CONVERT TO JSON]
                              │
                              ▼
               GEMINI STRUCTURED UNDERSTANDING
               (Dynamic Schema, Traceability,
                 Null for Missing Information)
                              │
                              ▼
                     HUMAN REVIEW / EDIT
                   (Structured JSON Editor)
                              │
               ┌──────────────┼──────────────┐
               ▼              ▼              ▼
           EXPORT JSON    EXPORT CSV    EXPORT TXT
               │              │              │
               └──────────────┼──────────────┘
                              ▼
                           DOWNLOAD
```

---

## 📁 Project Structure

Below is the repository's directory layout, mapping out the clean, decoupled organization of models, UI components, business logic services, utilities, and tests.

```text
Nobeth Universal OCR/
├── .env                        # Local configuration and API credentials (git-ignored)
├── .env.example                # Example template for environment configuration
├── .gitignore                  # Git untracked file configurations
├── app.py                      # Standalone Streamlit application entrypoint & state coordinator
├── README.md                   # Application documentation, architecture, and guides
├── requirements.txt            # Pinned dependency manifest
│
├── models/
│   ├── __init__.py             # Exposes core schema objects for cleaner imports
│   └── schemas.py              # Pydantic data models for readiness, extraction, and exports
│
├── prompts/
│   ├── __init__.py             # Package initializer for system and user prompt builders
│   ├── extraction_prompt.py    # Prompts enforcing verbatim, source-faithful vision extraction
│   └── structuring_prompt.py   # Prompts guiding dynamic document schema generation
│
├── services/
│   ├── __init__.py             # Exposes service client factories and orchestration functions
│   ├── export_service.py       # Implements JSON formatting, intelligent CSV flattening, and TXT builders
│   ├── extraction_service.py   # Orchestrates Stage 1 vision extraction and response parsing
│   ├── gemini_service.py       # Client wrapper with exponential backoff retries for Gemini API calls
│   ├── preprocessing_service.py# Orchestrates non-destructive page rendering and quality checks
│   └── structuring_service.py  # Orchestrates Stage 2 dynamic JSON structuring and field traceability
│
├── tests/
│   ├── __init__.py             # Test package initializer
│   ├── test_exports.py         # Verification of JSON, CSV, and plain-text export generation
│   ├── test_formats_and_pipeline.py # Integration testing for multi-page PDFs, WEBP, and TIFF formats
│   ├── test_preprocessing.py   # Verification of Laplacian blur, RMS contrast, brightness, and skew metrics
│   ├── test_structuring.py     # Verification of field traceability, leading zero preservation, and null mapping
│   └── test_validation.py      # Verification of upload bytes validator and resilient JSON repair heuristics
│
├── ui/
│   ├── __init__.py             # UI design system component exporter
│   ├── components.py           # Reusable visual components (Header, Stepper, Readiness panel, etc.)
│   └── theme.py                # CSS design system (fonts, tokens, custom radio tabs, and image containers)
│
├── utils/
│   ├── __init__.py             # Utility package initializer
│   ├── file_utils.py           # Format magic-byte signature check, MIME mappings, and file size formatting
│   ├── image_utils.py          # OpenCV calculations for quality metrics and non-destructive image preprocessing
│   ├── pdf_utils.py            # PyMuPDF-based adaptive rendering and PDF security checks
│   └── validation.py           # Upload byte verification and resilient fallback LLM JSON repair
│
└── sample_data/
    ├── sample_doc.pdf          # Sample multi-page PDF document for testing
    └── sample_invoice.jpg      # Sample invoice image for testing
```

### Detailed File Catalog & Purposes

#### Root Configuration & Entry Point
- **[app.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/app.py)**: The central application coordinator. It manages the Streamlit reactive UI, injects CSS, handles multi-page navigation, controls UI workflow stages (`EMPTY`, `UPLOADED`, `RAW_READY`, `STRUCTURED_READY`), tracks state, and handles user actions.
- **[requirements.txt](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/requirements.txt)**: Defines the exact versions of dependencies (like `streamlit`, `google-genai`, `opencv-python`, `PyMuPDF`, `pillow-heif`, etc.) required to build and run the application.
- **[.env](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/.env)**: Houses local secrets and config parameters, such as `GEMINI_API_KEY`, default model parameters, and maximum file size boundaries.

#### Model Schemas (`models/`)
- **[models/schemas.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/models/schemas.py)**: Defines all Pydantic models for structured validation and type guarantees across the system:
  - `MetricStatus` & `ReadinessStatus`: Ratings for document checks.
  - `ReadinessMetric` & `ReadinessReport`: Diagnostics for Resolution, Blur, Contrast, Brightness, and Skew.
  - `RawExtractionResult` & `PageExtraction`: Struct for verbatim outputs.
  - `StructuredExtractionResult` & `FieldTrace`: Holds structured JSON and field traceability linkages.
  - `ExportBundle`: Aggregates downstream downloadable strings.

#### Prompt Engineering (`prompts/`)
- **[prompts/extraction_prompt.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/prompts/extraction_prompt.py)**: Contains the visual system prompt instructions. It forces Gemini Vision to respect leading zeros, punctuation, tables, handwriting transcription, and verbatim spelling without altering names or guessing blurred numbers.
- **[prompts/structuring_prompt.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/prompts/structuring_prompt.py)**: Contains system prompts for Stage 2. It instructs Gemini to output raw JSON format with zero conversational markup, determine the document schema dynamically without domain assumptions, and output a `document_type` and `confidence_level`.

#### Business Logic Services (`services/`)
- **[services/gemini_service.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/services/gemini_service.py)**: Integrates with the official `google-genai` SDK. Implements bounded exponential backoff retry logic for rate limits (`429`), network dropouts, or temporary service failures, while failing immediately on authentication errors (`401`).
- **[services/preprocessing_service.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/services/preprocessing_service.py)**: Runs document quality assessment. Triggers PDF rendering or image loading, compiles quality diagnostics, and generates preprocessed image copies for OCR without changing original source bytes.
- **[services/extraction_service.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/services/extraction_service.py)**: Coordinates Stage 1 visual extraction. Passes preprocessed images to Gemini, processes pagination, and parses raw text blocks.
- **[services/structuring_service.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/services/structuring_service.py)**: Coordinates Stage 2. Feeds raw text to Gemini, validates the resulting JSON, and computes exact field-by-field source traceability.
- **[services/export_service.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/services/export_service.py)**: Translates dynamic JSON models to diverse exports. Includes an intelligent flattener to write nested dicts and list-of-lists matrices to clean tabular CSV records.

#### Visual Interface (`ui/`)
- **[ui/components.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/ui/components.py)**: Implements HTML rendering helpers for UI widgets (header bars, workflow steppers, warning lists, and quality grid chips).
- **[ui/theme.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/ui/theme.py)**: Implements the global design system stylesheet. Injects glassmorphism CSS styling, fonts, customized horizontal radio-tabs, and max-height constraints for document preview columns.

#### Utilities (`utils/`)
- **[utils/file_utils.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/utils/file_utils.py)**: Provides magic-byte format validation to guard the application against extension spoofing (supports JPG, PNG, WEBP, HEIC, TIFF, PDF).
- **[utils/image_utils.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/utils/image_utils.py)**: Computes computer vision metrics using OpenCV (Laplacian variance for blur, intensity standard deviation for contrast, and OTSU contour minAreaRect bounding boxes for skew angles). Generates non-destructive deskewed and contrast-enhanced copies.
- **[utils/pdf_utils.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/utils/pdf_utils.py)**: PyMuPDF wrapper that inspects PDF structure, checks encryption, and adaptively scales PDF pages to target DPIs based on page dimensions to avoid out-of-memory errors on massive blueprints.
- **[utils/validation.py](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/utils/validation.py)**: Performs upload verification and implements a resilient JSON repair pipeline that uses regex, bracket-stripping, and trailing-comma cleanups to rescue corrupted LLM structures.

#### Test Suite (`tests/`)
- Contains unit and integration tests confirming the stability, format parsing, quality assessment, JSON repair heuristics, and CSV flattening algorithms across Python 3.11.

---

## 🚀 Key Features

- **Single Application Server**: Runs with a single command (`streamlit run app.py`). No React, FastAPI, Node, MongoDB, Redis, Celery, or background workers.
- **Direct Gemini Vision Engine**: Original visual bytes are sent directly to `gemini-3.1-flash-lite`. OpenCV/Pillow are used solely for non-destructive quality checks.
- **Source-Faithful Raw Extraction**: Verbatim text preservation, retaining exact spelling, leading zeros (`00123`), financial amounts (`R 1,250.00`), markdown tables, and explicit uncertainty tokens (`INV-8?73`).
- **Dynamic AI Structuring**: Universal document understanding with zero hardcoded business rules. Missing values are cleanly mapped to `null`.
- **Field Traceability**: Links structured values back to their raw source representations.
- **Comprehensive Document Readiness**: Real-time OpenCV analysis evaluating Resolution, Blur (Laplacian variance), Contrast (RMS contrast), Exposure, and Skew with actionable warnings.
- **Adaptive PDF Support**: Renders multi-page PDFs adaptively to prevent memory exhaustion on high-resolution documents.
- **Human-in-the-Loop**: Interactive editor for raw text before JSON conversion, and structured JSON editor before export.
- **Lossless Multi-Format Export**: One-click downloads for formatted JSON (`.json`), tabular CSV (`.csv`), and text (`.txt`).
- **Cinematic Glassmorphic UI**: Custom dark theme with live status badges, responsive split workspace, and resilient session state handling.

---

## 📦 Supported File Formats

| Category | Formats |
| :--- | :--- |
| **Images** | `JPG`, `JPEG`, `PNG`, `WEBP`, `HEIC`, `TIFF`, `TIF` |
| **Documents** | `PDF` (single & multi-page) |

---

## 🛠️ Technology Stack & Dependencies

Tested and pinned on **Python 3.11**:

- `streamlit==1.46.0` - Modern reactive web workspace
- `google-genai==2.16.0` - Official Google GenAI Python SDK
- `pydantic==2.13.4` - Data validation and schemas
- `Pillow==11.3.0` & `pillow-heif==1.5.0` - Image loading and HEIC decoding
- `opencv-python==4.6.0.66` - Computer vision quality assessment & non-destructive deskew
- `numpy==1.24.4` - Array math for signal analysis
- `PyMuPDF==1.24.2` (`fitz`) - Fast adaptive PDF rendering
- `python-dotenv==1.2.2` - Environment variable management
- `pytest==7.4.0` - Automated testing

---

## ⚡ Quick Start

### 🚀 Windows One-Click Launch (Recommended)
For Windows users, we provide a fully automated, self-healing launcher. You do not need to manually configure virtual environments, activate terminal shells, or run pip packages.

1. Configure your `.env` file with your `GEMINI_API_KEY` (see the configuration template in `.env.example`).
2. Double-click **[run.bat](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/run.bat)** in the root folder (or run `./run.bat` from your terminal).
3. The launcher will automatically:
   - Scan for the best compatible system Python version (preferring `3.11` ➔ `3.10` ➔ `3.12` ➔ `3.13+`).
   - Create or verify a healthy `.venv` virtual environment.
   - Cache dependencies using a SHA-256 requirements hash and run import integrity checks.
   - Select an available local port automatically (starting with `8501`).
   - Start the Streamlit application server.
   - Auto-launch your default web browser directly to the application.

Detailed logs are written to **[logs/bootstrap.log](file:///g:/Nobeth%20Analytics/Projects/Nobeth%20Universal%20OCR/Codebase/logs/bootstrap.log)**.

---

### 🛠️ Manual CLI Developer Setup (macOS / Linux / Windows)
If you prefer manual command-line configuration, follow these instructions:

#### 1. Clone or Open the Workspace
Ensure you are in the project root directory:
```powershell
cd "g:\Nobeth Analytics\Projects\Nobeth Universal OCR\Codebase"
```

#### 2. Set Up Python Virtual Environment
**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

#### 4. Configure Environment Variables
Copy `.env.example` to `.env` and insert your Google Gemini API key:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.1-flash-lite
MAX_FILE_SIZE_MB=50
```

#### 5. Launch the Application
```powershell
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 🧪 Running Automated Tests

Run the full pytest suite:
```powershell
python -m pytest tests/ -v
```

### Test Suites Included:
- `tests/test_preprocessing.py`: Image quality metrics (Laplacian blur, RMS contrast, resolution) and non-destructive preprocessing.
- `tests/test_validation.py`: File format detection, corrupted PDF detection, and resilient JSON repair.
- `tests/test_structuring.py`: Field traceability, leading zero preservation, and null handling.
- `tests/test_exports.py`: JSON formatting, intelligent tabular CSV flattening for nested structures, and TXT generation.

---

## 🎯 Accuracy Philosophy & Limitations

- **Source Fidelity over Guessing**: If a character is degraded or illegible (e.g. `INV-8?73`), the engine explicitly preserves the uncertainty instead of guessing.
- **Zero Domain Biases**: The system does not assume any particular country, tax regime, or retailer catalog.
- **Non-Destructive Principle**: Preprocessing never modifies the original source bytes. The original image remains the reference of truth throughout the session.
- **Human-in-the-Loop**: Corrections made to raw text or structured JSON survive Streamlit page reruns and flow directly into final exports.

---

## 🔒 Security

- **Client-Side Protection**: The Gemini API key is loaded server-side only and is never exposed in the browser UI or DOM.
- **No Persistence Required**: Documents and extracted data exist solely within the active Streamlit session and are discarded upon session reset.
