#!/usr/bin/env python3
"""
Objective 2, Task 2.1: Create a manual test build task.

This script creates a hardcoded build task in sync_tasks.json
for testing the Hands execution pipeline end-to-end.

Usage:
    python scripts/create_test_build_task.py

The task will:
1. Build a Next.js landing page for a productized web development service
2. Use research findings from Brain's 'productized-services' domain
3. Be picked up by the scheduler's _execute_hands_tasks() in daemon mode
4. Or executed manually via: python -m cli.execution run <task_id>
"""

import sys
import os

# Add parent dir to path so we can import agent-brain modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sync import create_task

# Build brief from Brain's productized-services knowledge base research
BUILD_BRIEF = """
BUILD A LANDING PAGE: LaunchReady — Productized Next.js Landing Pages

TARGET USER: Startup founders (seed to Series A) who need a professional landing page
but are frustrated by freelancer unreliability (ghosting, scope creep, missed deadlines).

USER'S #1 PAIN: "I hired a freelance developer, they disappeared mid-project, and I
wasted 2 weeks and $3,000. I just need a landing page that converts — delivered on time."

VALUE PROPOSITION: Professional Next.js landing pages delivered in 48 hours. Fixed price.
No scope creep. No ghosting. Guaranteed delivery or money back.

KEY SELLING POINTS (from research):
- 72% of freelancers ghost clients at some point (2024 data)
- Scope creep affects 45-62% of tech projects
- SprintPage is the only direct competitor with similar transparent delivery
- Startup founders want: speed, reliability, modern tech stack, conversion-focused design

PRODUCT TIERS:
1. Starter ($497) — Single landing page, mobile responsive, 48-hour delivery
2. Growth ($997) — Landing page + 2 inner pages, animations, analytics setup
3. Scale ($1,997) — Full marketing site, CMS integration, A/B test ready

PAGE SECTIONS TO BUILD:
1. Hero — Bold headline about reliability + speed. CTA: "Get Your Page in 48 Hours"
2. Pain section — "Tired of freelancer drama?" Address ghosting, delays, scope creep
3. How it works — 3 steps: Brief → Build → Launch (with timeline)
4. Pricing — 3 tiers with feature comparison
5. Social proof — Testimonials (use realistic placeholder names, no stock photos)
6. FAQ — Address common objections (revisions, tech stack, what if I need changes)
7. Final CTA — "Stop waiting. Start launching." with email capture

TECH STACK: Next.js 15, Tailwind CSS, shadcn/ui, Framer Motion, Lucide icons
DEPLOY TO: Vercel (npx vercel --prod)
DESIGN: Modern, dark-mode-first, professional. Follow identity/design_system.md.
""".strip()

def main():
    task = create_task(
        title="Build LaunchReady landing page — productized Next.js service",
        description=BUILD_BRIEF,
        source_domain="productized-services",
        task_type="build",
        priority="high",
        metadata={
            "objective": "2.1",
            "purpose": "First Hands execution test — prove the pipeline works",
            "expected_output": "Live Vercel URL with a professional landing page",
            "tech_stack": ["nextjs", "tailwind", "shadcn-ui", "framer-motion"],
            "budget_cap": 0.50,
        },
    )
    
    print(f"✅ Test build task created!")
    print(f"   ID: {task['id']}")
    print(f"   Type: {task['task_type']}")
    print(f"   Priority: {task['priority']}")
    print(f"   Domain: {task['source_domain']}")
    print(f"   Title: {task['title']}")
    print(f"\nThe task is now in logs/sync_tasks.json and will be picked up by:")
    print(f"  - Daemon mode: scheduler._execute_hands_tasks()")
    print(f"  - Manual: python -m cli.execution run {task['id']}")
    print(f"\n⚠ This requires API budget to execute. Don't run until budget is available.")


if __name__ == "__main__":
    main()
