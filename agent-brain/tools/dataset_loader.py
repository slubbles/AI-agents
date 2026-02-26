"""
Dataset Loader — Pull code examples from HuggingFace datasets + GitHub.

Provides high-quality code reference data for Hands' exemplar memory
without burning API credits on generating examples from scratch.

Sources:
1. HuggingFace datasets (TypeScript/JavaScript/React code corpora)
2. GitHub raw files (curated repos for specific frameworks)
3. Local crawl data (from --crawl output)

This is complementary to web research — datasets provide code patterns,
web research provides current ecosystem knowledge.
"""

import json
import os
import re
import logging
from typing import Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

# HuggingFace datasets API
HF_API_BASE = "https://huggingface.co/api/datasets"
HF_DATASETS_BASE = "https://datasets-server.huggingface.co"

# Curated dataset mappings per domain
DOMAIN_DATASETS = {
    "nextjs-react": [
        {"source": "hf", "id": "Devendra174/react-code-dataset", "description": "React code patterns"},
        {"source": "hf", "id": "mhhmm/typescript-instruct-20k", "description": "TypeScript instruction/completion pairs"},
    ],
    "typescript": [
        {"source": "hf", "id": "mhhmm/typescript-instruct-20k", "description": "TypeScript instruction/completion pairs"},
        {"source": "hf", "id": "mhhmm/typescript-instruct-20k-v2c", "description": "TypeScript instruct v2"},
    ],
    "python": [
        {"source": "hf", "id": "codeparrot/github-code", "description": "GitHub code corpus"},
    ],
}

# Curated GitHub repos per domain (raw file URLs)
DOMAIN_GITHUB_REPOS = {
    "nextjs-react": [
        {"repo": "vercel/next.js", "paths": ["examples/with-typescript/app/page.tsx", "examples/with-typescript/app/layout.tsx"]},
        {"repo": "vercel/ai", "paths": ["examples/next-openai/app/api/chat/route.ts"]},
    ],
}

# Local cache directory
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dataset_cache")


def _ensure_cache_dir():
    """Create cache directory if it doesn't exist."""
    os.makedirs(CACHE_DIR, exist_ok=True)


def _get_cache_path(source: str, identifier: str) -> str:
    """Get cache file path for a dataset/file."""
    safe_id = re.sub(r'[^\w\-.]', '_', identifier)
    return os.path.join(CACHE_DIR, f"{source}_{safe_id}.json")


def _is_cached(source: str, identifier: str, max_age_hours: int = 24) -> Optional[list]:
    """Check if data is cached and fresh enough."""
    import time
    cache_path = _get_cache_path(source, identifier)
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < max_age_hours * 3600:
            try:
                with open(cache_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
    return None


def _save_cache(source: str, identifier: str, data: list):
    """Save data to cache."""
    _ensure_cache_dir()
    cache_path = _get_cache_path(source, identifier)
    try:
        with open(cache_path, "w") as f:
            json.dump(data, f)
    except IOError as e:
        logger.warning(f"Failed to cache {identifier}: {e}")


def fetch_hf_dataset_samples(
    dataset_id: str,
    split: str = "train",
    max_samples: int = 50,
    text_field: str = "content",
) -> list[dict]:
    """
    Fetch sample rows from a HuggingFace dataset.
    
    Uses the HuggingFace datasets server API (no auth needed for public datasets).
    
    Returns:
        List of {content, source, metadata} dicts
    """
    # Check cache first
    cached = _is_cached("hf", f"{dataset_id}_{split}_{max_samples}")
    if cached:
        logger.info(f"Using cached data for {dataset_id}")
        return cached
    
    import urllib.request
    import urllib.error
    
    # Try the datasets server first-rows endpoint
    url = f"{HF_DATASETS_BASE}/first-rows?dataset={quote(dataset_id, safe='')}&config=default&split={split}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentBrain/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to fetch HF dataset {dataset_id}: {e}")
        # Try alternative config names
        for config in ["plain_text", "all", dataset_id.split("/")[-1]]:
            try:
                alt_url = f"{HF_DATASETS_BASE}/first-rows?dataset={quote(dataset_id, safe='')}&config={config}&split={split}"
                req = urllib.request.Request(alt_url, headers={"User-Agent": "AgentBrain/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())
                break
            except Exception:
                continue
        else:
            return []

    rows = data.get("rows", [])[:max_samples]
    
    results = []
    for row in rows:
        row_data = row.get("row", row)
        
        # Try common field names for code content
        content = ""
        for field in [text_field, "content", "code", "text", "input", "instruction", "output", "completion"]:
            if field in row_data and isinstance(row_data[field], str):
                content = row_data[field]
                if len(content) > 50:  # Only accept meaningful content
                    break
        
        if not content or len(content) < 50:
            continue
        
        results.append({
            "content": content[:5000],  # Cap per sample
            "source": f"hf:{dataset_id}",
            "metadata": {
                "split": split,
                "fields": list(row_data.keys())[:10],
            }
        })
    
    # Cache results
    if results:
        _save_cache("hf", f"{dataset_id}_{split}_{max_samples}", results)
    
    return results


def fetch_github_file(repo: str, path: str, branch: str = "main") -> Optional[dict]:
    """
    Fetch a single file from GitHub (raw content).
    
    Returns:
        {content, source, metadata} dict or None
    """
    # Check cache first
    cache_key = f"{repo}_{path}_{branch}"
    cached = _is_cached("github", cache_key, max_age_hours=168)  # Week-long cache for GitHub
    if cached:
        return cached[0] if cached else None
    
    import urllib.request
    import urllib.error
    
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentBrain/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        logger.debug(f"Failed to fetch GitHub file {repo}/{path}: {e}")
        return None
    
    if not content or len(content) < 20:
        return None
    
    result = {
        "content": content[:10000],  # Cap at 10K
        "source": f"github:{repo}/{path}",
        "metadata": {
            "repo": repo,
            "path": path,
            "branch": branch,
            "language": _detect_language(path),
        }
    }
    
    _save_cache("github", cache_key, [result])
    return result


def _detect_language(path: str) -> str:
    """Detect language from file extension."""
    ext_map = {
        ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript",
        ".py": "python",
        ".json": "json",
        ".css": "css", ".scss": "scss",
    }
    ext = os.path.splitext(path)[1].lower()
    return ext_map.get(ext, "unknown")


def load_crawl_data(domain: str) -> list[dict]:
    """
    Load locally crawled documentation data.
    
    Reads from crawl_data/{domain}/ directory (output of --crawl).
    Returns content formatted for exemplar injection.
    """
    crawl_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "crawl_data", domain)
    
    if not os.path.isdir(crawl_dir):
        return []
    
    results = []
    for filename in os.listdir(crawl_dir):
        if not filename.endswith(".json"):
            continue
        
        filepath = os.path.join(crawl_dir, filename)
        try:
            with open(filepath) as f:
                data = json.load(f)
            
            pages = data.get("pages", [])
            for page in pages:
                if page.get("content_length", 0) > 100:
                    results.append({
                        "content": page["content"][:5000],
                        "source": f"crawl:{page.get('url', filename)}",
                        "metadata": {
                            "title": page.get("title", ""),
                            "headings": page.get("headings", [])[:10],
                            "domain": domain,
                        }
                    })
        except (json.JSONDecodeError, IOError) as e:
            logger.debug(f"Error loading crawl data {filename}: {e}")
    
    return results


def get_domain_examples(domain: str, max_examples: int = 20) -> list[dict]:
    """
    Get code examples for a domain from all sources.
    
    Combines:
    1. HuggingFace datasets (if configured for domain)
    2. GitHub reference files (if configured for domain)
    3. Local crawl data (if available)
    
    Returns list of {content, source, metadata} dicts.
    """
    examples = []
    
    # 1. HuggingFace datasets
    datasets = DOMAIN_DATASETS.get(domain, [])
    for ds in datasets:
        if ds["source"] == "hf":
            samples = fetch_hf_dataset_samples(ds["id"], max_samples=max_examples // len(datasets) if datasets else max_examples)
            examples.extend(samples)
            logger.info(f"Loaded {len(samples)} samples from HF:{ds['id']}")
    
    # 2. GitHub reference files
    repos = DOMAIN_GITHUB_REPOS.get(domain, [])
    for repo_config in repos:
        for path in repo_config["paths"]:
            result = fetch_github_file(repo_config["repo"], path)
            if result:
                examples.append(result)
                logger.info(f"Loaded GitHub file: {repo_config['repo']}/{path}")
    
    # 3. Local crawl data
    crawl_data = load_crawl_data(domain)
    examples.extend(crawl_data[:max_examples])
    if crawl_data:
        logger.info(f"Loaded {len(crawl_data[:max_examples])} crawl pages for {domain}")
    
    return examples[:max_examples]


def inject_examples_into_strategy(
    domain: str,
    strategy: str,
    max_examples: int = 5,
    max_chars_per_example: int = 1500,
) -> str:
    """
    Inject code examples from datasets into execution strategy.
    
    This gives Hands concrete reference patterns to follow
    when generating code, without any API cost.
    """
    examples = get_domain_examples(domain, max_examples=max_examples)
    
    if not examples:
        return strategy
    
    # Build examples block
    examples_block = "\n\n=== REFERENCE CODE EXAMPLES (from datasets) ===\n"
    examples_block += "Use these as style/pattern references when writing code:\n\n"
    
    for i, ex in enumerate(examples[:max_examples], 1):
        content = ex["content"][:max_chars_per_example]
        source = ex["source"]
        examples_block += f"--- Example {i} (from {source}) ---\n"
        examples_block += content
        examples_block += "\n\n"
    
    examples_block += "=== END REFERENCE EXAMPLES ===\n"
    
    return strategy + examples_block
