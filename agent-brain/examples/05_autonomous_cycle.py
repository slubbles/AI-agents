#!/usr/bin/env python3
"""
Example: Self-Directed Learning Cycle

Demonstrates the autonomous research loop:
1. Question Generator diagnoses knowledge gaps
2. Generates research questions
3. Researcher investigates
4. Critic scores output
5. Meta-Analyst evolves strategy
6. Repeat

Run:
    python examples/05_autonomous_cycle.py

Cost: ~$0.10-0.15 per round
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def example_diagnose_gaps():
    """Show knowledge gaps in a domain."""
    print("\n=== STEP 1: Diagnose Knowledge Gaps ===\n")
    
    print("  CLI command:")
    print("  python main.py --kb --domain productized-services")
    print("")
    print("  Current gaps for productized-services:")
    print("    [HIGH] Freelancer project abandonment rates")
    print("    [HIGH] Platform-specific completion rates")
    print("    [HIGH] React/Next.js project metrics")
    print("    [MEDIUM] Founder testimonials for switching")
    print("    [LOW] QA processes for productized services")


def example_generate_questions():
    """Generate next research questions."""
    print("\n=== STEP 2: Generate Research Questions ===\n")
    
    print("  CLI command:")
    print("  python main.py --next --domain productized-services")
    print("")
    print("  This analyzes gaps and generates:")
    print("    - Ranked questions by priority")
    print("    - Questions that fill multiple gaps")
    print("    - Reasoning for each question")


def example_single_round():
    """Run a single research round."""
    print("\n=== STEP 3: Single Research Round ===\n")
    
    print("  CLI command:")
    print("  python main.py --domain productized-services 'Your research question'")
    print("")
    print("  This runs the full cycle:")
    print("    1. Researcher searches web")
    print("    2. Fetches full page content")
    print("    3. Produces structured findings")
    print("    4. Critic scores on 5 dimensions")
    print("    5. Accepts (≥6) or rejects (<6)")
    print("    6. Stores in memory with score")


def example_auto_rounds():
    """Run multiple autonomous rounds."""
    print("\n=== STEP 4: Autonomous Multi-Round ===\n")
    
    print("  CLI command (3 rounds):")
    print("  python main.py --auto --rounds 3 --domain productized-services")
    print("")
    print("  Each round:")
    print("    1. Question Generator picks highest-priority gap")
    print("    2. Generates research question")
    print("    3. Researcher investigates")
    print("    4. Critic scores")
    print("    5. KB synthesized")
    print("    6. Strategy evolved (every 3 outputs)")


def example_strategy_evolution():
    """Show strategy evolution."""
    print("\n=== STEP 5: Strategy Evolution ===\n")
    
    print("  After 3+ outputs, meta-analyst kicks in:")
    print("")
    print("  CLI command (force evolution):")
    print("  python main.py --evolve --domain productized-services")
    print("")
    print("  CLI command (view strategy status):")
    print("  python main.py --status --domain productized-services")
    print("")
    print("  Evolution cycle:")
    print("    1. Analyze last N scored outputs")
    print("    2. Find patterns in high vs low scores")
    print("    3. Generate new strategy version")
    print("    4. New strategy enters 'trial' (3 outputs)")
    print("    5. If score improves → 'active'")
    print("    6. If score drops → rollback")


def example_full_autonomous():
    """Full autonomous operation."""
    print("\n=== FULL AUTONOMOUS MODE ===\n")
    
    print("  # Run 10 self-directed rounds")
    print("  python main.py --auto --rounds 10 --domain productized-services")
    print("")
    print("  What happens:")
    print("    Round 1-3:  Fill highest-priority gaps")
    print("    After 3:    Meta-analyst evolves strategy")
    print("    Round 4-6:  Research with new strategy (trial)")
    print("    After 6:    Evaluate trial, promote or rollback")
    print("    Round 7-10: Continue with proven strategy")
    print("")
    print("  Expected outcome:")
    print("    - 6-8 accepted outputs")
    print("    - Strategy v001 → v002 if improved")
    print("    - KB claims: 26 → 35+")
    print("    - Gaps: 9 → 5-6")


def main():
    print("\n" + "="*60)
    print("  SELF-DIRECTED LEARNING CYCLE")
    print("  (Fully Autonomous Research)")
    print("="*60)
    
    example_diagnose_gaps()
    example_generate_questions()
    example_single_round()
    example_auto_rounds()
    example_strategy_evolution()
    example_full_autonomous()
    
    print("\n" + "="*60)
    print("  COST ESTIMATES")
    print("="*60 + "\n")
    
    print("  Single question:     ~$0.05-0.10")
    print("  --auto --rounds 3:   ~$0.30-0.40")
    print("  --auto --rounds 10:  ~$1.00-1.50")
    print("  Full domain buildout: ~$3.00-5.00")


if __name__ == "__main__":
    main()
