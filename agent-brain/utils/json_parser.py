"""
Shared JSON extraction utility.
Robust parser that handles LLM output with preamble text, markdown fences,
and nested JSON objects. Used by all agents for consistent parsing.
"""

import json
import re


def extract_json(text: str, expected_keys: set[str] | None = None) -> dict | None:
    """
    Extract a JSON object from text that may contain preamble or markdown fencing.
    
    Handles common LLM output patterns:
    - Markdown code fences (```json ... ```)
    - Preamble text before JSON
    - Multiple JSON objects (picks the best match)
    - Truncated JSON (attempts to close brackets)
    
    Args:
        text: Raw LLM output text
        expected_keys: Optional set of keys to prefer when multiple JSON objects found.
                       Defaults to general research keys.
    
    Returns:
        Parsed dict, or None if no valid JSON found
    """
    if expected_keys is None:
        expected_keys = set()

    # Strip ALL markdown code fences (including nested ones)
    text = re.sub(r'```(?:json)?\s*\n?', '', text)
    text = text.strip()

    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Strategy: find all balanced JSON objects and pick the best one
    candidates = []

    # Find all top-level '{' positions
    i = 0
    while i < len(text):
        if text[i] == '{':
            # Track depth to find the matching '}'
            depth = 0
            in_string = False
            escape_next = False
            j = i
            for j in range(i, len(text)):
                c = text[j]
                if escape_next:
                    escape_next = False
                    continue
                if c == '\\' and in_string:
                    escape_next = True
                    continue
                if c == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        fragment = text[i:j + 1]
                        try:
                            obj = json.loads(fragment)
                            if isinstance(obj, dict):
                                candidates.append(obj)
                        except json.JSONDecodeError:
                            pass
                        break
            i = j + 1 if depth == 0 else i + 1
        else:
            i += 1

    # Pick the candidate with the most expected keys
    if candidates:
        if expected_keys:
            scored = [(len(expected_keys & set(c.keys())), len(c), c) for c in candidates]
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
            return scored[0][2]
        else:
            # No expected keys — return the largest object
            candidates.sort(key=lambda c: len(c), reverse=True)
            return candidates[0]

    # Last resort: try from first { to end with manual closing
    brace_start = text.find('{')
    if brace_start == -1:
        return None

    fragment = text[brace_start:]
    for suffix in ['"}]}', '"}]', '"}', '}']:
        try:
            result = json.loads(fragment + suffix)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            continue

    return None
