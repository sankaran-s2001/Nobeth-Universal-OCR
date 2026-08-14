"""Gemini API client service layer with bounded retries and resilient error handling."""

import os
import time
from typing import Any, List, Optional, Union
from dotenv import load_dotenv
from PIL import Image
from google import genai
from google.genai import types
import streamlit as st

# Load environment variables
load_dotenv()


def get_gemini_api_key() -> Optional[str]:
    """Retrieves the Gemini API key from environment variables."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return key if key else None


def get_gemini_model_id() -> str:
    """Retrieves the configured model ID from environment or defaults to stable gemini-3.1-flash-lite."""
    return os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()


@st.cache_resource(show_spinner=False)
def get_cached_genai_client(api_key: str) -> genai.Client:
    """
    Initializes and caches the Google GenAI client instance.
    Cached per API key to prevent unnecessary client recreation across Streamlit reruns.
    """
    return genai.Client(api_key=api_key)


class GeminiService:
    """Service layer for Gemini vision extraction and dynamic structuring."""

    def __init__(self, api_key: Optional[str] = None, model_id: Optional[str] = None):
        self.api_key = api_key or get_gemini_api_key()
        self.model_id = model_id or get_gemini_model_id()
        self.max_retries = 3
        self.initial_backoff_sec = 2.0

        if not self.api_key:
            raise ValueError(
                "Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file."
            )

        self.client = get_cached_genai_client(self.api_key)

    def _execute_with_retry(self, api_func, *args, **kwargs) -> Any:
        """
        Executes a Gemini API function with bounded exponential backoff for transient errors.
        """
        last_exception = None
        backoff = self.initial_backoff_sec

        for attempt in range(1, self.max_retries + 1):
            try:
                return api_func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                err_msg = str(e).lower()

                # Check for rate limits or transient errors
                is_transient = any(
                    token in err_msg
                    for token in ["429", "quota", "resource_exhausted", "503", "unavailable", "timeout", "deadline"]
                )

                # Check for fatal authentication errors (do not retry)
                is_auth_error = any(
                    token in err_msg
                    for token in ["401", "unauthenticated", "invalid_argument", "api_key_invalid", "api key not valid"]
                )

                if is_auth_error:
                    raise ValueError(
                        "Gemini API authentication failed. Please verify that your GEMINI_API_KEY in .env is valid."
                    ) from e

                if is_transient and attempt < self.max_retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                else:
                    break

        raise RuntimeError(
            f"Gemini API request failed after {self.max_retries} attempts: {str(last_exception)}"
        ) from last_exception

    def generate_vision_content(
        self,
        image_or_images: Union[Image.Image, List[Image.Image]],
        system_instruction: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> str:
        """
        Calls Gemini Vision on single image or list of images.
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

        def _call():
            return self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=config,
            )

        response = self._execute_with_retry(_call)

        if not response or not response.text:
            raise ValueError("Gemini returned an empty extraction response.")

        return response.text.strip()

    def generate_text_content(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> str:
        """
        Calls Gemini for text-based dynamic structuring.
        """
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
        )

        def _call():
            return self.client.models.generate_content(
                model=self.model_id,
                contents=[user_prompt],
                config=config,
            )

        response = self._execute_with_retry(_call)

        if not response or not response.text:
            raise ValueError("Gemini returned an empty structuring response.")

        return response.text.strip()


def get_gemini_service() -> GeminiService:
    """Factory helper to obtain configured GeminiService instance."""
    return GeminiService()
