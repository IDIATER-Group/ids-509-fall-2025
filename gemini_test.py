import os
from llm_providers import generate_text

os.environ.setdefault("LLM_PROVIDER", "gemini")
os.environ.setdefault("GEMINI_MODEL", "gemini-1.5-flash")
os.environ.setdefault("GOOGLE_API_KEY", "AIzaSyDZ1hkeltOGVCVMT6h_lRZGNpyfIgwDOeY")

print(generate_text("Reply with exactly three words: hello from gemini"))
