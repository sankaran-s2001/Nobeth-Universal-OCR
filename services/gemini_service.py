"""Gemini API client service layer with bounded retries, dynamic model failover, and resilient error handling."""

import os
import time
from typing import Any, Callable, List, Optional, Union
from dotenv import load_dotenv
from PIL import Image
from google import genai
from google.genai import types
import streamlit as st

# Load environment variables
load_dotenv()

PRIMARY_MODEL_DEFAULT = "gemini-3.1-flash-lite"
FALLBACK_MODEL_DEFAULT = "gemini-3.5-flash-lite"


def get_gemini_api_key() -> Optional[str]:
    """Retrieves the Gemini API key from environment variables."""
    raw = os.getenv("GEMINI_API_KEY", "")
    key = raw.strip().strip('"').strip("'")
    if key and key not in ["your_gemini_api_key_here", "your_actual_key_here", "None"]:
        return key
    return None


def get_gemini_model_id() -> str:
    """Retrieves the configured primary model ID from environment or defaults to stable gemini-3.1-flash-lite."""
    return os.getenv("GEMINI_MODEL", PRIMARY_MODEL_DEFAULT).strip()


def get_gemini_fallback_model_id() -> str:
    """Retrieves the fallback model ID used when primary model experiences high demand or rate limits."""
    return os.getenv("GEMINI_FALLBACK_MODEL", FALLBACK_MODEL_DEFAULT).strip()


@st.cache_resource(show_spinner=False)
def get_cached_genai_client(api_key: str) -> genai.Client:
    """
    Initializes and caches the Google GenAI client instance.
    Cached per API key to prevent unnecessary client recreation across Streamlit reruns.
    Configures a 60-second timeout (60,000 milliseconds in google-genai SDK) to prevent socket hangs.
    """
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=60_000),
    )



def _format_compact_error(err: Exception) -> str:
    """Returns a short, clean error summary for telemetry log output."""
    msg = str(err).strip()
    msg_lower = msg.lower()
    for code in [
        "504 deadline_exceeded",
        "503 unavailable",
        "429 resource_exhausted",
        "502 bad_gateway",
        "500 internal",
    ]:
        if code in msg_lower:
            return code.upper()
    if "deadline expired" in msg_lower or "504" in msg_lower:
        return "504 DEADLINE_EXCEEDED"
    if "high demand" in msg_lower or "503" in msg_lower:
        return "503 UNAVAILABLE (high demand)"
    if "handshake operation timed out" in msg_lower or "_ssl.c" in msg_lower:
        return "TLS handshake timed out"
    if "429" in msg_lower or "quota" in msg_lower:
        return "429 RESOURCE_EXHAUSTED"
    first_line = msg.split("\n")[0].strip()
    return first_line[:75] + ("..." if len(first_line) > 75 else "")


class GeminiService:
    """Service layer for Gemini vision extraction and dynamic structuring with automatic model fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_id: Optional[str] = None,
        fallback_model_id: Optional[str] = None,
    ):
        self.api_key = api_key or get_gemini_api_key()
        self.primary_model_id = model_id or get_gemini_model_id()
        self.fallback_model_id = fallback_model_id or get_gemini_fallback_model_id()
        self.active_model_id = self.primary_model_id
        self.is_fallback_active = False
        self.max_retries_per_model = 2
        self.initial_backoff_sec = 1.5

        if not self.api_key:
            raise ValueError(
                "Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file."
            )

        self.client = get_cached_genai_client(self.api_key)

    @property
    def model_id(self) -> str:
        """Backward-compatible property exposing active model ID."""
        return self.active_model_id

    def _execute_with_failover(
        self,
        call_factory: Callable[[str], Any],
        op_id: Optional[str] = None,
        stage_name: str = "GEMINI_API",
        on_model_switch: Optional[Callable[[str], None]] = None,
    ) -> Any:
        """
        Executes a Gemini API call with alternating (ping-pong) failover between primary
        and fallback models upon capacity spikes, timeouts (504 DEADLINE_EXCEEDED),
        rate limits (429), or network transient errors:
          Attempt 1: Primary Model (gemini-3.1-flash-lite)
          Attempt 2: Fallback Model (gemini-3.5-flash-lite)
          Attempt 3: Primary Model (gemini-3.1-flash-lite)
          Attempt 4: Fallback Model (gemini-3.5-flash-lite)
        """
        op_tag = op_id or "API"
        has_fallback = bool(
            self.fallback_model_id and self.fallback_model_id != self.primary_model_id
        )

        if has_fallback:
            candidate_sequence = [
                self.primary_model_id,
                self.fallback_model_id,
                self.primary_model_id,
                self.fallback_model_id,
            ]
        else:
            candidate_sequence = [self.primary_model_id, self.primary_model_id]

        total_attempts = len(candidate_sequence)
        last_exception = None

        for attempt_idx, target_model in enumerate(candidate_sequence, start=1):
            is_fallback_candidate = (target_model != self.primary_model_id)
            self.active_model_id = target_model
            self.is_fallback_active = is_fallback_candidate

            t0 = time.perf_counter()
            try:
                result = call_factory(target_model)
                call_dur = time.perf_counter() - t0
                if op_id:
                    from utils.telemetry import log_stage_success
                    tag = f"Attempt {attempt_idx}/{total_attempts} OK ({target_model})"
                    if is_fallback_candidate:
                        tag += " [FALLBACK]"
                    log_stage_success(op_tag, "GEMINI_NETWORK", call_dur, tag)
                return result
            except Exception as e:
                call_dur = time.perf_counter() - t0
                last_exception = e
                err_msg = str(e).lower()

                # Fatal authentication errors do not retry and do not failover
                is_auth_error = any(
                    token in err_msg
                    for token in [
                        "401",
                        "unauthenticated",
                        "invalid_argument",
                        "api_key_invalid",
                        "api key not valid",
                    ]
                )
                if is_auth_error:
                    raise ValueError(
                        "Gemini API authentication failed. Please verify that your GEMINI_API_KEY in .env is valid."
                    ) from e

                # Check for transient, capacity, deadline, timeout, or server connection errors
                is_transient = any(
                    token in err_msg
                    for token in [
                        "503",
                        "unavailable",
                        "high demand",
                        "spikes in demand",
                        "service unavailable",
                        "504",
                        "deadline_exceeded",
                        "deadline expired",
                        "gateway timeout",
                        "502",
                        "bad gateway",
                        "500",
                        "internal",
                        "429",
                        "quota",
                        "resource_exhausted",
                        "rate limit",
                        "too many requests",
                        "timeout",
                        "timed out",
                        "handshake operation timed out",
                        "connection reset",
                        "remotely closed",
                        "forcibly closed",
                        "broken pipe",
                        "transport error",
                        "econnreset",
                        "connection error",
                        "network error",
                        "_ssl.c",
                    ]
                )

                if not is_transient:
                    # Non-transient error, abort retry loop
                    break

                if attempt_idx < total_attempts:
                    next_model = candidate_sequence[attempt_idx]
                    short_err = _format_compact_error(e)
                    if op_id:
                        from utils.telemetry import log_stage_retry
                        log_stage_retry(
                            op_tag,
                            stage_name,
                            attempt_idx,
                            call_dur,
                            f"{target_model}: {short_err} -> Switching to {next_model}",
                        )
                    if on_model_switch:
                        try:
                            on_model_switch(next_model)
                        except Exception:
                            pass

                    backoff = min(1.0 * (1.5 ** (attempt_idx - 1)), 3.0)
                    time.sleep(backoff)
                else:
                    break

        unique_models = list(dict.fromkeys(candidate_sequence))
        if "timeout" in str(last_exception).lower() or "deadline" in str(last_exception).lower():
            raise TimeoutError(
                f"Gemini API request timed out across {total_attempts} attempts on models ({', '.join(unique_models)}): {str(last_exception)}"
            ) from last_exception

        raise RuntimeError(
            f"Gemini API request failed across {total_attempts} attempts on models ({', '.join(unique_models)}): {str(last_exception)}"
        ) from last_exception

    def generate_vision_content(
        self,
        image_or_images: Union[Image.Image, List[Image.Image]],
        system_instruction: str,
        user_prompt: str,
        temperature: float = 0.1,
        op_id: Optional[str] = None,
        on_model_switch: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Calls Gemini Vision on single image or list of images with automated model failover.
        """
        contents: List[Any] = []
        if isinstance(image_or_images, list):
            contents.extend(image_or_images)
        else:
            contents.append(image_or_images)
        contents.append(user_prompt)

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
        )

        def _call(model_name: str):
            return self.client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )

        response = self._execute_with_failover(
            _call,
            op_id=op_id,
            stage_name="VISION_OCR",
            on_model_switch=on_model_switch,
        )

        if not response or not response.text:
            raise ValueError("Gemini returned an empty extraction response.")

        return response.text.strip()

    def generate_text_content(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: float = 0.0,
        op_id: Optional[str] = None,
        on_model_switch: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Calls Gemini for text-based dynamic structuring with automated model failover.
        """
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
        )

        def _call(model_name: str):
            return self.client.models.generate_content(
                model=model_name,
                contents=[user_prompt],
                config=config,
            )

        response = self._execute_with_failover(
            _call,
            op_id=op_id,
            stage_name="JSON_STRUCTURING",
            on_model_switch=on_model_switch,
        )

        if not response or not response.text:
            raise ValueError("Gemini returned an empty structuring response.")

        return response.text.strip()


def get_gemini_service() -> GeminiService:
    """Factory helper to obtain configured GeminiService instance."""
    return GeminiService()
