import requests
from typing import List, Dict, Optional

OLLAMA_URL = "http://localhost:11434/api/chat"

def ollama_chat(model: str, messages: List[Dict], temperature: float = 0.7) -> str:
    payload = {"model": model, "messages": messages, "options": {"temperature": temperature}, "stream": False}
    r = requests.post(OLLAMA_URL, json=payload, timeout=180)
    r.raise_for_status()
    return r.json()["message"]["content"]

def ollama_vision(model: str, user_text: str, image_b64: str, system: Optional[str] = None) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_text, "images": [image_b64]})
    payload = {"model": model, "messages": messages, "stream": False}
    r = requests.post(OLLAMA_URL, json=payload, timeout=180)
    r.raise_for_status()
    return r.json()["message"]["content"]