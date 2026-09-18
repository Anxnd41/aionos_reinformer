"""
gemini_client.py — wrapper for LLM providers (OpenRouter, Ollama, or Mock).

Exposes a single function:
    generate_json(system_prompt, user_prompt) -> dict

Supports three modes:
  1. Mock mode (rule-based, no LLM, works offline)
  2. Local Ollama (free, no API key, runs on your machine)
  3. OpenRouter API (requires OPENROUTER_API_KEY)

Set USE_MOCK_MODE=true in .env for instant offline operation.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Mode selection
USE_MOCK_MODE = os.environ.get("USE_MOCK_MODE", "false").lower() == "true"
USE_LOCAL_LLM = os.environ.get("USE_LOCAL_LLM", "false").lower() == "true"

# OpenRouter settings
OPENROUTER_MODEL = "google/gemini-flash-1.5"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Ollama settings (local)
OLLAMA_MODEL = "llama3.2:3b"
OLLAMA_API_URL = "http://localhost:11434/api/chat"

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0

_api_key: str | None = None


# ---------------------------------------------------------------------------
# Mock Mode (Rule-Based Extraction)
# ---------------------------------------------------------------------------

def _mock_extract_commitments(user_prompt: str) -> dict[str, Any]:
    """Rule-based commitment extraction using pattern matching."""
    commitments = []
    
    # Look for common commitment patterns
    patterns = [
        r"(?:I'll|I will|I'm going to|going to|need to|have to|must|should)\s+(.+?)(?:\.|by|before|$)",
        r"(?:send|give|provide|deliver|share|email)\s+(.+?)(?:to|by|before|\.|$)",
        r"(?:review|check|confirm|verify|follow up on)\s+(.+?)(?:\.|by|before|$)",
        r"(?:deadline|due|by)\s+(\w+)",
    ]
    
    # Extract text from the prompt (simple heuristic)
    lines = user_prompt.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 10:
            continue
            
        # Check for commitment indicators
        has_commitment = any(word in line.lower() for word in [
            "will", "going to", "need to", "should", "must",
            "send", "deliver", "provide", "review", "confirm",
            "deadline", "due", "by", "eod", "end of day"
        ])
        
        if has_commitment:
            # Extract potential deadline
            deadline = None
            for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
                if day in line.lower():
                    deadline = day.capitalize()
                    break
            
            if "tomorrow" in line.lower():
                deadline = "tomorrow"
            elif "today" in line.lower():
                deadline = "today"
            elif "eod" in line.lower() or "end of day" in line.lower():
                deadline = "EOD today"
            
            # Create commitment
            commitment = {
                "title": line[:100],  # First 100 chars
                "description": line,
                "owner": "Arjun Malhotra",  # Default from sources
                "counterparty": None,
                "raw_deadline": deadline,
                "completed": "done" in line.lower() or "completed" in line.lower()
            }
            commitments.append(commitment)
    
    # If no commitments found, return empty list
    if not commitments:
        commitments = [{
            "title": "Review sources",
            "description": "Extracted from meeting/email content",
            "owner": "Arjun Malhotra",
            "counterparty": None,
            "raw_deadline": "Friday",
            "completed": False
        }]
    
    return {"commitments": commitments}


def _mock_dedupe(user_prompt: str) -> dict[str, Any]:
    """Mock deduplication - just groups by similar titles."""
    # Extract commitment IDs from prompt
    ids = re.findall(r'"id":\s*"([^"]+)"', user_prompt)
    
    if not ids:
        return {"groups": []}
    
    # Simple grouping: each item is its own group (no actual deduplication in mock mode)
    groups = [[id] for id in ids]
    
    return {"groups": groups}


def _mock_brief(user_prompt: str) -> dict[str, Any]:
    """Generate a simple text brief."""
    brief = f"""# Daily Brief — 2026-09-25

## 📋 Summary
Commitments extracted from meeting transcripts, emails, calendars, and voice notes.

## ⚠ Overdue Items
- Review and send vendor list to Raghav
- Complete expense variance report

## 📅 Due Today (Friday, Sept 25)
- Sign Mumbai office lease renewal paperwork
- Final review before board meeting

## 🔜 Upcoming This Week
- Q3 campaign deck review
- Follow up on client commitments

*Note: Mock mode is active - using rule-based extraction. Enable LLM for better results.*
"""
    return {"brief": brief}


def _mock_qa(user_prompt: str) -> dict[str, Any]:
    """Mock Q&A responses."""
    question_lower = user_prompt.lower()
    
    if "overdue" in question_lower:
        answer = "Based on the extracted commitments, there are 2 overdue items: the vendor list for Raghav and the expense variance report."
    elif "today" in question_lower or "due" in question_lower:
        answer = "Today (Friday, Sept 25), you have: Mumbai office lease renewal and board meeting preparation."
    elif "who" in question_lower:
        answer = "The main commitments involve Arjun Malhotra (you), with tasks for Raghav, Neha, and Divya."
    else:
        answer = "Based on the commitment data, you have several pending tasks across meetings, emails, and calendars. Use the daily brief for a full overview."
    
    return {"answer": answer}


def _call_mock(system_prompt: str, user_prompt: str) -> str:
    """Call mock rule-based processor."""
    prompt_lower = user_prompt.lower()
    
    # Detect intent from prompt content
    if "extract" in system_prompt.lower() or "commitment" in system_prompt.lower():
        result = _mock_extract_commitments(user_prompt)
    elif "dedupe" in system_prompt.lower() or "group" in prompt_lower or "duplicate" in prompt_lower:
        result = _mock_dedupe(user_prompt)
    elif "brief" in system_prompt.lower() or "daily" in prompt_lower:
        result = _mock_brief(user_prompt)
    elif "question" in system_prompt.lower() or "answer" in prompt_lower or "?" in user_prompt:
        result = _mock_qa(user_prompt)
    else:
        # Default fallback
        result = {"commitments": []}
    
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Local LLM (Ollama)
# ---------------------------------------------------------------------------

def _call_ollama(system_prompt: str, user_prompt: str) -> str:
    """Call local Ollama API."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    json_instruction = (
        "\n\nIMPORTANT: Your response must be valid JSON. "
        "Do not include any text before or after the JSON object."
    )
    messages.append({"role": "user", "content": user_prompt + json_instruction})
    
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": "json",
    }
    
    response = requests.post(OLLAMA_API_URL, json=payload, timeout=120)
    response.raise_for_status()
    result = response.json()
    
    if "message" in result and "content" in result["message"]:
        return result["message"]["content"].strip()
    else:
        raise ValueError(f"Unexpected Ollama response: {result}")


# ---------------------------------------------------------------------------
# Cloud LLM (OpenRouter)
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    """Get OpenRouter API key."""
    global _api_key
    if _api_key is not None:
        return _api_key
    
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY is not set. "
            "Options:\n"
            "  1. Set USE_MOCK_MODE=true for offline rule-based mode\n"
            "  2. Set USE_LOCAL_LLM=true and install Ollama\n"
            "  3. Add OpenRouter key from https://openrouter.ai/keys"
        )
    
    _api_key = api_key
    return _api_key


def _call_openrouter(system_prompt: str, user_prompt: str) -> str:
    """Call OpenRouter API."""
    api_key = _get_api_key()
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/aionos-executive-agent",
        "X-Title": "Executive Productivity Agent",
    }
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
    }
    
    response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    result = response.json()
    
    if "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0]["message"]["content"].strip()
    else:
        raise ValueError(f"Unexpected OpenRouter response: {result}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """
    Call LLM provider and return parsed JSON.
    
    Modes (in order of precedence):
      1. Mock mode (USE_MOCK_MODE=true) - rule-based, offline
      2. Local Ollama (USE_LOCAL_LLM=true) - free, no API key
      3. OpenRouter API - cloud, requires key
    """
    if USE_MOCK_MODE:
        provider = "Mock (rule-based, offline)"
        print(f"[llm_client] Using {provider}")
        raw_text = _call_mock(system_prompt, user_prompt)
        return json.loads(raw_text)
    
    provider = "Ollama (local)" if USE_LOCAL_LLM else "OpenRouter (cloud)"
    print(f"[llm_client] Using {provider}")
    
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if USE_LOCAL_LLM:
                raw_text = _call_ollama(system_prompt, user_prompt)
            else:
                raw_text = _call_openrouter(system_prompt, user_prompt)
            
            # Strip markdown fences
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
                raw_text = re.sub(r"\n?```$", "", raw_text.strip())

            return json.loads(raw_text)

        except Exception as exc:
            last_error = exc
            print(f"[llm_client] Attempt {attempt}/{MAX_RETRIES}: Error — {exc}")
            
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE ** attempt
                print(f"[llm_client] Waiting {wait:.0f}s before retry...")
                time.sleep(wait)

    raise RuntimeError(
        f"LLM API call failed after {MAX_RETRIES} attempts. "
        f"Provider: {provider}. Last error: {last_error}"
    )
