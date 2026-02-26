"""
Crawl-to-KB Bridge — Convert crawled documentation into Knowledge Base claims.

Takes the output of --crawl (stored in crawl_data/) and produces
structured claims that feed directly into the domain's knowledge base.
This enables offline learning from documentation without API calls.

Pipeline:
1. Read crawl data (JSON files from Scrapling crawls)
2. Extract structured claims from each page
3. Store as scored claims in the KB (synthetic score = 7, source = "crawl")
4. Researcher can then build on this pre-loaded knowledge
"""

import json
import os
import re
import logging
import hashlib
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _extract_claims_from_page(page: dict) -> list[dict]:
    """
    Extract factual claims from a crawled page's content.
    
    Uses heuristic extraction (no LLM needed):
    - Sentences with specific patterns (numbers, comparisons, API names)
    - Code patterns and their descriptions
    - Heading-based topic identification
    """
    content = page.get("content", "")
    title = page.get("title", "")
    url = page.get("url", "")
    headings = page.get("headings", [])
    
    claims = []
    
    # Split content into sentences
    sentences = re.split(r'(?<=[.!?])\s+', content)
    
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 30 or len(sentence) > 500:
            continue
        
        # Score sentence relevance
        score = 0
        
        # Technical indicators
        if re.search(r'\b(API|function|method|class|component|hook|prop|state|render|import|export)\b', sentence, re.IGNORECASE):
            score += 2
        
        # Specific data (numbers, versions, sizes)
        if re.search(r'\b\d+(\.\d+)*\b', sentence):
            score += 1
        
        # Comparisons / best practices
        if re.search(r'\b(should|must|recommend|best practice|prefer|avoid|instead of|rather than|better|faster|slower)\b', sentence, re.IGNORECASE):
            score += 2
        
        # Definitions
        if re.search(r'\b(is a|refers to|means|defined as|consists of)\b', sentence, re.IGNORECASE):
            score += 1
        
        # Code references
        if re.search(r'`[^`]+`|<code>|<\/code>', sentence):
            score += 1
        
        if score >= 2:
            # Find which heading this belongs under
            topic = title
            for h in headings:
                if h.lower() in content[:content.find(sentence)].lower():
                    topic = h
            
            claims.append({
                "claim": sentence,
                "confidence": "medium",
                "source": url,
                "topic": topic,
                "extraction_score": score,
            })
    
    return claims


def crawl_to_claims(domain: str, max_claims_per_page: int = 10) -> list[dict]:
    """
    Convert all crawled data for a domain into structured claims.
    
    Returns:
        List of claim dicts ready for KB injection.
    """
    crawl_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "crawl_data", domain)
    
    if not os.path.isdir(crawl_dir):
        logger.info(f"No crawl data for domain '{domain}'")
        return []
    
    all_claims = []
    seen_claims = set()  # Dedup by content hash
    
    for filename in sorted(os.listdir(crawl_dir)):
        if not filename.endswith(".json"):
            continue
        
        filepath = os.path.join(crawl_dir, filename)
        try:
            with open(filepath) as f:
                data = json.load(f)
            
            pages = data.get("pages", [])
            for page in pages:
                page_claims = _extract_claims_from_page(page)
                
                # Sort by extraction score, take top N
                page_claims.sort(key=lambda c: c.get("extraction_score", 0), reverse=True)
                
                for claim in page_claims[:max_claims_per_page]:
                    # Dedup
                    claim_hash = hashlib.md5(claim["claim"].encode()).hexdigest()[:12]
                    if claim_hash not in seen_claims:
                        seen_claims.add(claim_hash)
                        all_claims.append(claim)
        
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Error reading crawl data {filename}: {e}")
    
    logger.info(f"Extracted {len(all_claims)} unique claims from crawl data for '{domain}'")
    return all_claims


def inject_crawl_claims_into_kb(domain: str, max_claims: int = 100) -> dict:
    """
    Inject crawled claims into the domain's knowledge base.
    
    Creates synthetic scored entries that the researcher can build on.
    
    Returns:
        {injected: int, skipped: int, total_claims: int}
    """
    from memory_store import load_knowledge_base, save_knowledge_base
    
    claims = crawl_to_claims(domain, max_claims_per_page=10)
    if not claims:
        return {"injected": 0, "skipped": 0, "total_claims": 0}
    
    # Load existing KB
    kb = load_knowledge_base(domain) or {"claims": [], "domain_summary": "", "last_updated": ""}
    existing_claims = {c.get("claim", "")[:80] for c in kb.get("claims", [])}
    
    injected = 0
    skipped = 0
    
    for claim in claims[:max_claims]:
        # Skip if similar claim already exists
        if claim["claim"][:80] in existing_claims:
            skipped += 1
            continue
        
        kb_claim = {
            "claim": claim["claim"],
            "confidence": claim.get("confidence", "medium"),
            "status": "active",
            "source": claim.get("source", "crawl"),
            "topic": claim.get("topic", ""),
            "added_by": "crawl_injector",
            "added_at": datetime.now().isoformat(),
            "score": 7,  # Synthetic score — docs are generally accurate
        }
        kb["claims"].append(kb_claim)
        existing_claims.add(claim["claim"][:80])
        injected += 1
    
    if injected > 0:
        kb["last_updated"] = datetime.now().isoformat()
        save_knowledge_base(domain, kb)
        logger.info(f"Injected {injected} claims into KB for '{domain}' (skipped {skipped} duplicates)")
    
    return {"injected": injected, "skipped": skipped, "total_claims": len(claims)}
