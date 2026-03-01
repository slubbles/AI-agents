"""
LLM Router — Multi-provider abstraction for cost optimization.

Routes LLM calls to different providers based on model configuration:
- Claude models → Anthropic API (direct)
- OpenRouter models → OpenRouter API (OpenAI-compatible)

This allows using cheap models (Deepseek V3 via OpenRouter) for high-volume
low-stakes tasks (researcher, question generator) while keeping Claude Sonnet
for critical tasks (critic, verifier, meta-analyst).

Usage:
    from llm_router import call_llm
    
    response = call_llm(
        model=MODELS["researcher"],
        system="...",
        messages=[...],
        tools=[...],  # optional
        max_tokens=4096,
    )

The response format is normalized to match Anthropic's response structure,
regardless of which provider handled the request.
"""

import os
import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("llm_router")

# ============================================================
# Provider Detection
# ============================================================

def is_claude_model(model: str) -> bool:
    """Check if model should be routed to Anthropic."""
    return model.startswith("claude-")


def is_openrouter_model(model: str) -> bool:
    """Check if model should be routed via OpenRouter."""
    # OpenRouter model format: provider/model-name
    return "/" in model or model.startswith("deepseek") or model.startswith("llama")


# ============================================================
# Response Normalization
# ============================================================

@dataclass
class Usage:
    """Token usage tracking (Anthropic-compatible)."""
    input_tokens: int
    output_tokens: int


@dataclass
class TextBlock:
    """Text content block (Anthropic-compatible)."""
    type: str = "text"
    text: str = ""


@dataclass  
class ToolUseBlock:
    """Tool use content block (Anthropic-compatible)."""
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = None
    
    def __post_init__(self):
        if self.input is None:
            self.input = {}


@dataclass
class NormalizedResponse:
    """Normalized response matching Anthropic's structure."""
    content: list
    stop_reason: str
    usage: Usage
    model: str


def _normalize_openrouter_response(response, model: str) -> NormalizedResponse:
    """Convert OpenRouter (OpenAI-format) response to Anthropic format."""
    choice = response.choices[0]
    message = choice.message
    
    content = []
    
    # Handle text content
    if message.content:
        content.append(TextBlock(type="text", text=message.content))
    
    # Handle tool calls
    if hasattr(message, 'tool_calls') and message.tool_calls:
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}
            content.append(ToolUseBlock(
                type="tool_use",
                id=tc.id,
                name=tc.function.name,
                input=args,
            ))
    
    # Map stop reason
    stop_reason_map = {
        "stop": "end_turn",
        "tool_calls": "tool_use",
        "length": "max_tokens",
        "content_filter": "end_turn",
    }
    stop_reason = stop_reason_map.get(choice.finish_reason, "end_turn")
    
    # Usage
    usage = Usage(
        input_tokens=response.usage.prompt_tokens if response.usage else 0,
        output_tokens=response.usage.completion_tokens if response.usage else 0,
    )
    
    return NormalizedResponse(
        content=content,
        stop_reason=stop_reason,
        usage=usage,
        model=model,
    )


# ============================================================
# Provider Clients (lazy initialization)
# ============================================================

_anthropic_client = None
_openrouter_client = None


def _get_anthropic_client():
    """Get or create Anthropic client."""
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        _anthropic_client = Anthropic(api_key=api_key)
    return _anthropic_client


def _get_openrouter_client():
    """Get or create OpenRouter client (OpenAI-compatible)."""
    global _openrouter_client
    if _openrouter_client is None:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required for OpenRouter. Run: pip install openai")
        
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set. Get one at https://openrouter.ai/keys")
        
        _openrouter_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    return _openrouter_client


# ============================================================
# Tool Format Conversion
# ============================================================

def _convert_tools_to_openai_format(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool format to OpenAI/OpenRouter format."""
    if not tools:
        return None
    
    openai_tools = []
    for tool in tools:
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            }
        }
        openai_tools.append(openai_tool)
    
    return openai_tools


def _convert_messages_to_openai_format(messages: list[dict], system: str = None) -> list[dict]:
    """Convert Anthropic message format to OpenAI format."""
    openai_messages = []
    
    # Add system message first
    if system:
        openai_messages.append({"role": "system", "content": system})
    
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        # Handle content that's a list (Anthropic format)
        if isinstance(content, list):
            # Convert content blocks to text
            text_parts = []
            tool_results = []
            
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        tool_results.append(block)
                elif isinstance(block, str):
                    text_parts.append(block)
            
            if text_parts:
                openai_messages.append({
                    "role": role,
                    "content": "\n".join(text_parts),
                })
            
            # Handle tool results
            for tr in tool_results:
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": tr.get("tool_use_id", ""),
                    "content": tr.get("content", ""),
                })
        else:
            openai_messages.append({
                "role": role,
                "content": str(content),
            })
    
    return openai_messages


# ============================================================
# Main Router Function
# ============================================================

def call_llm(
    model: str,
    messages: list[dict],
    system: str = None,
    max_tokens: int = 4096,
    tools: list[dict] = None,
    temperature: float = 0.7,
    **kwargs
) -> NormalizedResponse:
    """
    Route LLM call to appropriate provider based on model name.
    
    Args:
        model: Model identifier (e.g., "claude-sonnet-4-20250514" or "deepseek/deepseek-chat")
        messages: List of message dicts with role and content
        system: System prompt (optional)
        max_tokens: Maximum tokens to generate
        tools: List of tool definitions (Anthropic format)
        temperature: Sampling temperature
        **kwargs: Additional provider-specific arguments
    
    Returns:
        NormalizedResponse with Anthropic-compatible structure
    """
    
    if is_claude_model(model):
        return _call_anthropic(model, messages, system, max_tokens, tools, temperature, **kwargs)
    else:
        return _call_openrouter(model, messages, system, max_tokens, tools, temperature, **kwargs)


def _call_anthropic(
    model: str,
    messages: list[dict],
    system: str,
    max_tokens: int,
    tools: list[dict],
    temperature: float,
    **kwargs
) -> NormalizedResponse:
    """Call Anthropic API directly."""
    from utils.retry import retry_api_call
    
    client = _get_anthropic_client()
    
    call_kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    
    if system:
        call_kwargs["system"] = system
    if tools:
        call_kwargs["tools"] = tools
    
    # Don't pass temperature to Anthropic if not needed
    # (some models have default temp)
    
    response = retry_api_call(
        lambda: client.messages.create(**call_kwargs),
        max_attempts=5,
        base_delay=15.0,
        verbose=True,
    )
    
    # Anthropic response is already in correct format
    return response


def _call_openrouter(
    model: str,
    messages: list[dict],
    system: str,
    max_tokens: int,
    tools: list[dict],
    temperature: float,
    **kwargs
) -> NormalizedResponse:
    """Call OpenRouter API (OpenAI-compatible)."""
    client = _get_openrouter_client()
    
    # Convert to OpenAI format
    openai_messages = _convert_messages_to_openai_format(messages, system)
    openai_tools = _convert_tools_to_openai_format(tools)
    
    call_kwargs = {
        "model": model,
        "messages": openai_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    
    if openai_tools:
        call_kwargs["tools"] = openai_tools
    
    # Add OpenRouter-specific headers
    call_kwargs["extra_headers"] = {
        "HTTP-Referer": "https://github.com/slubbles/AI-agents",
        "X-Title": "Agent Brain",
    }
    
    # Simple retry logic for OpenRouter
    import time
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            response = client.chat.completions.create(**call_kwargs)
            return _normalize_openrouter_response(response, model)
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            logger.warning(f"OpenRouter call failed (attempt {attempt + 1}): {e}")
            time.sleep(5 * (attempt + 1))
    
    raise RuntimeError("OpenRouter call failed after retries")


# ============================================================
# Convenience: Check Provider Availability
# ============================================================

def check_providers() -> dict:
    """Check which providers are configured and available."""
    status = {
        "anthropic": {
            "configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "available": False,
        },
        "openrouter": {
            "configured": bool(os.environ.get("OPENROUTER_API_KEY")),
            "available": False,
        },
    }
    
    if status["anthropic"]["configured"]:
        try:
            _get_anthropic_client()
            status["anthropic"]["available"] = True
        except Exception:
            pass
    
    if status["openrouter"]["configured"]:
        try:
            _get_openrouter_client()
            status["openrouter"]["available"] = True
        except Exception:
            pass
    
    return status


# ============================================================
# Model Mapping (for config.py integration)
# ============================================================

# Cheap models via OpenRouter
OPENROUTER_MODELS = {
    "grok-4.1-fast": "x-ai/grok-4.1-fast",
    "deepseek-v3": "deepseek/deepseek-chat",
    "deepseek-r1": "deepseek/deepseek-reasoner",
    "llama-3.3-70b": "meta-llama/llama-3.3-70b-instruct",
    "llama-3.1-8b": "meta-llama/llama-3.1-8b-instruct",
    "gemini-flash": "google/gemini-2.0-flash-001",
    "mistral-large": "mistralai/mistral-large-2411",
}

# Cost per 1M tokens (for tracking)
MODEL_COSTS = {
    # Claude (Anthropic)
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    # Deepseek via OpenRouter
    "deepseek/deepseek-chat": {"input": 0.27, "output": 1.10},
    "x-ai/grok-4.1-fast": {"input": 0.50, "output": 2.00},  # Grok 4.1 Fast
    "deepseek/deepseek-reasoner": {"input": 0.55, "output": 2.19},
    # Llama via OpenRouter
    "meta-llama/llama-3.3-70b-instruct": {"input": 0.59, "output": 0.79},
    "meta-llama/llama-3.1-8b-instruct": {"input": 0.05, "output": 0.08},
    # Gemini via OpenRouter  
    "google/gemini-2.0-flash-001": {"input": 0.075, "output": 0.30},
}


def get_model_cost(model: str) -> dict:
    """Get cost per 1M tokens for a model."""
    return MODEL_COSTS.get(model, {"input": 1.0, "output": 5.0})
