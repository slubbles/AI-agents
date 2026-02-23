# Agent Brain

Self-improving autonomous research agent system.

## Architecture

```
Question → Researcher → Critic (scores 1-10) → Quality Gate → Memory
                ↑                                      |
                └──── retry with critique if score < 6 ─┘
```

## Setup

```bash
cd agent-brain
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python main.py "your research question here"
```

## Structure

- `agents/` — agent role implementations (researcher, critic)
- `memory/` — scored outputs stored as JSON (per domain)
- `strategies/` — versioned strategy documents per agent per domain
- `logs/` — full loop execution logs
- `config.py` — model assignments, thresholds, paths
- `main.py` — loop runner entry point
