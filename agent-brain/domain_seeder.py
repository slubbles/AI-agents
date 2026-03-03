"""
Domain Seeder — Bootstrap New Research Domains

Provides seed questions for domains that have zero outputs.
The orchestrator can use these to bootstrap domains without
requiring manual input.

Seed questions are curated to be:
- Broad enough to establish a knowledge baseline
- Specific enough to produce high-quality research
- Time-aware (reference current developments)
- Scored to prioritize the most foundational questions

No API calls — pure configuration.
"""

from datetime import date


# ============================================================
# Seed Question Templates
# ============================================================

# Domain-specific seed questions — ordered by priority (first = most foundational)
SEED_QUESTIONS = {
    "crypto": [
        "What are the current major cryptocurrency market trends, top assets by market cap, and key regulatory developments?",
        "What are the latest developments in Bitcoin ETFs and institutional crypto adoption?",
        "What is the current state of DeFi protocols, their total value locked, and major security incidents?",
        "What are the most significant stablecoin developments and regulatory actions?",
        "What are the latest developments in blockchain scalability solutions and layer 2 networks?",
    ],
    "cybersecurity": [
        "What are the most significant cybersecurity threats and vulnerabilities actively being exploited right now?",
        "What are the latest developments in AI-powered cybersecurity defense and attack techniques?",
        "What major data breaches and security incidents have occurred recently, and what were their impacts?",
        "What is the current state of ransomware attacks, including major incidents and law enforcement responses?",
        "What are the emerging cybersecurity regulations and compliance requirements globally?",
    ],
    "ai": [
        "What are the most significant recent developments in artificial intelligence research and large language models?",
        "What are the current capabilities and limitations of frontier AI models, and how are they being deployed?",
        "What are the major AI safety and alignment research developments and policy proposals?",
        "What is the current state of AI regulation globally, including the EU AI Act and US executive orders?",
        "What are the latest developments in autonomous AI agents and multi-agent systems?",
    ],
    "geopolitics": [
        "What are the most significant geopolitical developments and international relations shifts happening right now?",
        "What is the current state of major global conflicts and peace negotiations?",
        "What are the latest developments in US-China relations and their global implications?",
        "What major trade agreements, sanctions, or economic policy shifts are affecting the global economy?",
        "What are the most significant developments in global energy security and climate policy?",
    ],
    "physics": [
        "What are the most significant recent discoveries and breakthroughs in physics?",
        "What is the current state of quantum computing research and its most promising approaches?",
        "What are the latest developments in fusion energy research and when might commercial fusion become viable?",
        "What recent discoveries have been made at CERN or other particle physics laboratories?",
        "What is the current state of dark matter and dark energy research?",
    ],
    "economics": [
        "What are the current major global economic trends, including GDP growth, inflation, and employment?",
        "What are the latest central bank monetary policy decisions and their market impacts?",
        "What is the current state of global trade and supply chain dynamics?",
        "What are the most significant developments in digital currencies and central bank digital currencies?",
        "What are the latest developments in housing markets and real estate across major economies?",
    ],
    "biotech": [
        "What are the most significant recent breakthroughs in biotechnology and genetic engineering?",
        "What is the current state of mRNA technology applications beyond COVID vaccines?",
        "What are the latest developments in CRISPR gene editing and its therapeutic applications?",
        "What major clinical trial results have been announced recently, and what are their implications?",
        "What are the current developments in longevity research and anti-aging therapies?",
    ],
    "climate": [
        "What are the latest climate science findings and how do they compare to previous projections?",
        "What are the most significant developments in renewable energy technology and deployment?",
        "What are the current global carbon emission trends and progress toward net-zero targets?",
        "What major climate policy developments and international agreements have occurred recently?",
        "What are the latest developments in carbon capture and removal technologies?",
    ],
    "space": [
        "What are the most significant recent developments in space exploration and commercial spaceflight?",
        "What is the current state of the Artemis program and plans for returning to the Moon?",
        "What are the latest developments in Mars exploration, including rovers and future crewed mission plans?",
        "What recent astronomical discoveries have been made using the James Webb Space Telescope?",
        "What is the current state of the satellite internet industry and space debris management?",
    ],
    "nextjs-react": [
        "What are the current best practices for Next.js App Router architecture, including when to use Server Components vs Client Components and how to structure layouts and routes?",
        "What are the most effective React component composition patterns in 2025-2026, including compound components, render props alternatives, and the latest hooks patterns?",
        "What are the current best practices for data fetching and caching in Next.js App Router, including Server Actions, React Server Components data patterns, and cache invalidation strategies?",
        "What are the most important React 19 features and patterns, including use() hook, Actions, useOptimistic, and how they change component architecture?",
        "What are the current best practices for styling and design systems in Next.js applications, including Tailwind CSS patterns, CSS Modules vs styled-components tradeoffs, and responsive design approaches?",
    ],
    "web-design": [
        "What makes a web application look production-ready in 2025-2026? What specific visual patterns separate professional SaaS products from amateur projects? Include shadcn/ui, Tailwind CSS, and Framer Motion best practices.",
        "What are the current best practices for SaaS landing page design that converts? Include hero section structure, social proof placement, CTA design, pricing table patterns, and above-the-fold content rules.",
        "What are the specific Tailwind CSS 4 patterns, spacing systems, and responsive design techniques used by top-tier SaaS products? Include typography scales, color system strategies, and dark mode implementation.",
        "What are the current best practices for micro-interactions, loading states, empty states, error states, and skeleton screens in modern web applications? Include Framer Motion animation patterns with specific code examples.",
        "What are the anti-patterns in modern web design — things that immediately make a site look cheap or unprofessional? Include typography mistakes, spacing errors, color system failures, and mobile responsiveness problems.",
    ],
}

# Generic seed questions for any domain not in the list above
GENERIC_SEEDS = [
    "What are the most significant recent developments and current state of {domain}?",
    "What are the major challenges and emerging trends in {domain}?",
    "What key research breakthroughs or discoveries have recently occurred in {domain}?",
    "Who are the most influential organizations and researchers in {domain}, and what are they working on?",
    "What are the most important open questions and knowledge gaps in {domain}?",
]


def get_seed_questions(domain: str, count: int = 1) -> list[str]:
    """
    Get seed questions for a domain.
    
    Args:
        domain: The research domain
        count: Number of questions to return (default: 1)
    
    Returns:
        List of seed question strings
    """
    domain_lower = domain.lower()
    
    if domain_lower in SEED_QUESTIONS:
        curated = SEED_QUESTIONS[domain_lower]
        questions = curated[:count]
        # If requesting more than available curated seeds, pad with generic
        if count > len(curated):
            generic = [q.replace("{domain}", domain) for q in GENERIC_SEEDS]
            questions.extend(generic[:count - len(curated)])
    else:
        questions = [q.replace("{domain}", domain) for q in GENERIC_SEEDS[:count]]
    
    return questions


def get_seed_question(domain: str) -> str:
    """
    Get the top-priority seed question for a domain.
    
    Returns:
        A seed question string
    """
    questions = get_seed_questions(domain, count=1)
    return questions[0] if questions else f"What are the most important current developments in {domain}?"


def list_available_domains() -> list[str]:
    """List all domains that have curated seed questions."""
    return sorted(SEED_QUESTIONS.keys())


def has_curated_seeds(domain: str) -> bool:
    """Check if a domain has curated (non-generic) seed questions."""
    return domain.lower() in SEED_QUESTIONS
