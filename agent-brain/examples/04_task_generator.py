#!/usr/bin/env python3
"""
Example: Task Generator (Brain → Hands Bridge)

Demonstrates how the KB generates actionable coding tasks:
1. Analyze KB claims
2. Identify knowledge gaps
3. Generate coding tasks with reasoning
4. Execute with Hands (optional)

Run:
    python examples/04_task_generator.py

Cost: ~$0.05 for task generation, ~$0.20-0.50 for execution
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def example_show_kb():
    """Show KB status for a domain."""
    print("\n=== STEP 1: View KB Status ===\n")
    
    print("  CLI command:")
    print("  python main.py --kb --domain productized-services")
    print("")
    print("  This shows:")
    print("    - Active claims (26 for productized-services)")
    print("    - Knowledge gaps (9 identified)")
    print("    - Topics covered")
    print("    - Confidence levels")


def example_generate_tasks():
    """Generate coding tasks from KB."""
    print("\n=== STEP 2: Generate Coding Tasks ===\n")
    
    print("  CLI command:")
    print("  python main.py --next-task --domain productized-services")
    print("")
    print("  This analyzes the KB and generates 3 ranked tasks:")
    print("")
    print("  Example output:")
    print("  [1] (medium) Build a Freelancer Risk Calculator")
    print("      Reasoning: Claims 1, 2, 6, 9 establish ghosting rates...")
    print("      Applies KB: Claim 1 (ghosting), Claim 3 (70% under 35)...")
    print("")
    print("  [2] (medium) Create a Cost Comparison Tool")
    print("      Reasoning: Claims 10-11 establish SprintPage pricing...")
    print("")
    print("  [3] (low) Build a Platform Analyzer")
    print("      Reasoning: Claims 12-14 show platform sizes...")


def example_execute_task():
    """Execute a task with Hands."""
    print("\n=== STEP 3: Execute with Hands ===\n")
    
    print("  CLI command (specific goal):")
    print("  python main.py --domain productized-services --execute \\")
    print("                 --goal 'Create a Python CLI that calculates freelancer risk'")
    print("")
    print("  CLI command (auto-pick from generated tasks):")
    print("  python main.py --domain productized-services --auto-build")
    print("")
    print("  This will:")
    print("    1. Generate a plan (Planner agent)")
    print("    2. Execute step-by-step (Executor agent)")
    print("    3. Validate output (Validator agent)")
    print("    4. Save artifacts to output/<domain>/")


def example_full_cycle():
    """Show the complete Brain→Hands cycle."""
    print("\n=== FULL BRAIN→HANDS CYCLE ===\n")
    
    print("  # 1. View KB (understand what Brain knows)")
    print("  python main.py --kb --domain productized-services")
    print("")
    print("  # 2. Generate task candidates")
    print("  python main.py --next-task --domain productized-services")
    print("")
    print("  # 3. Execute top task")
    print("  python main.py --auto-build --domain productized-services")
    print("")
    print("  # 4. Check execution history")
    print("  python main.py --exec-status --domain productized-services")


def show_current_tasks():
    """Show actual tasks that would be generated."""
    print("\n=== CURRENT TASK CANDIDATES ===\n")
    
    try:
        from hands.task_generator import generate_tasks
        
        # This would call the API - just show the structure
        print("  Tasks are generated from:")
        print("    - KB claims (26 active)")
        print("    - Knowledge gaps (9 identified)")
        print("    - Domain context")
        print("")
        print("  Each task includes:")
        print("    - Priority (high/medium/low)")
        print("    - Description")
        print("    - Reasoning (which claims support it)")
        print("    - Dependencies")
        print("")
        print("  Run --next-task to see actual generated tasks")
        
    except Exception as e:
        print(f"  Note: {e}")


def main():
    print("\n" + "="*60)
    print("  TASK GENERATOR EXAMPLE")
    print("  (Brain → Hands Bridge)")
    print("="*60)
    
    example_show_kb()
    example_generate_tasks()
    example_execute_task()
    example_full_cycle()
    show_current_tasks()


if __name__ == "__main__":
    main()
