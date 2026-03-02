# Cortex — Risk Tolerance

How much the system is allowed to gamble per domain and per action. This calibrates the tension between exploration (trying new things) and exploitation (doing what works).

## General Risk Policy

**Conservative by default, with earned escalation.**

The system starts risk-averse. As a domain accumulates data and strategies prove effective, risk tolerance can increase. But never faster than the evidence supports.

## Risk Tiers

### Tier 1: Proven Domains (10+ accepted outputs, active strategy)
- **Budget allocation:** Up to 40% of daily budget
- **Strategy experimentation:** May trial new strategies without extra caution
- **Research scope:** Can explore adjacent questions beyond the core goal
- **Round cap:** Up to 5 rounds per cycle

### Tier 2: Developing Domains (3-10 accepted outputs, strategy evolving)
- **Budget allocation:** Up to 25% of daily budget
- **Strategy experimentation:** New strategies must beat baseline by ≥0.5 in trial period
- **Research scope:** Stay focused on core goal questions
- **Round cap:** Up to 3 rounds per cycle

### Tier 3: New Domains (0-2 accepted outputs, seed phase)
- **Budget allocation:** Up to 15% of daily budget
- **Strategy experimentation:** Use seed strategy from cross-domain principles first
- **Research scope:** Stick to foundational questions — understand the landscape before going deep
- **Round cap:** Up to 2 rounds per cycle

## Cost Risk

- Never spend more than $0.50 on a single research round (if estimated cost exceeds this, flag and skip)
- If daily spend reaches 80% of limit, switch to minimum-cost operations only
- If a domain consistently produces low scores (<5.5 avg over 5 rounds), reduce its allocation or pause it

## Strategy Risk

- Never deploy a strategy that scored >20% below the current best without human review
- Never run more than one trial strategy per domain simultaneously
- If a trial strategy fails evaluation, revert immediately — don't give it a second chance

## Exploration vs. Exploitation

- **80% exploitation, 20% exploration** as default
- Exploitation: research questions directly aligned with the domain goal
- Exploration: adjacent questions that might reveal new insights or opportunities
- For new domains, invert: 20% exploitation, 80% exploration (need to understand the landscape first)
