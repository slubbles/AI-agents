#!/usr/bin/env python3
"""
Example: Basic Research Cycle

Demonstrates the core Brain loop:
1. Ask a research question
2. Researcher searches + fetches pages
3. Critic scores the output
4. Memory stores the result

Run:
    python examples/01_basic_research.py

Cost: ~$0.05-0.10 per question
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import _run_research_cycle


def main():
    # Example: Research productized services market
    question = "What are the pricing models for productized landing page services in 2025?"
    domain = "productized-services"
    
    print(f"\n{'='*60}")
    print(f"  RESEARCH QUESTION")
    print(f"  Domain: {domain}")
    print(f"  Question: {question}")
    print(f"{'='*60}\n")
    
    # Run the cycle (will use API credits)
    # Uncomment to actually run:
    # result = _run_research_cycle(domain, question)
    # print(f"\nResult: {result}")
    
    print("(Dry run - uncomment the code to actually run)")
    print("\nTo run manually:")
    print(f'  python main.py --domain {domain} "{question}"')


if __name__ == "__main__":
    main()
