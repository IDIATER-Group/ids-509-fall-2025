# llm_providers.py
import os
from typing import Optional

MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

def generate_text(prompt: str, system: Optional[str] = None, temperature: float = 0.0) -> str:
    """
    Generic text generation using Google AI Studio (Gemini).
    Replace old Ollama calls with this function.
    """
    provider = os.getenv("LLM_PROVIDER", "gemini")
    if provider != "gemini":
        raise RuntimeError("Set LLM_PROVIDER=gemini to use Gemini Flash via AI Studio.")

    import google.generativeai as genai
    api_key = os.environ["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(
        model_name=MODEL,
        system_instruction=system
    )

    response = model.generate_content(
        prompt,
        generation_config={"temperature": temperature}
    )

    return (response.text or "").strip()
