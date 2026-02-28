# Examples

Runnable examples demonstrating Cortex capabilities.

## Quick Reference

| Example | Description | Cost |
|---------|-------------|------|
| [01_basic_research.py](01_basic_research.py) | Single research question | ~$0.05-0.10 |
| [02_vault_browser.py](02_vault_browser.py) | Store creds, auth fetch | FREE (no API) |
| [03_crawl_to_kb.py](03_crawl_to_kb.py) | Crawl docs → KB → RAG | FREE (no API) |
| [04_task_generator.py](04_task_generator.py) | KB → coding tasks | ~$0.05-0.50 |
| [05_autonomous_cycle.py](05_autonomous_cycle.py) | Self-directed learning | ~$0.10-1.50 |

## Running Examples

```bash
cd agent-brain

# View example (dry run)
python examples/01_basic_research.py

# Run with actual API calls
python main.py --domain productized-services "Your question here"
```

## Common CLI Commands

```bash
# Research
python main.py --domain DOMAIN "question"       # Single question
python main.py --auto --rounds 5 --domain D     # 5 autonomous rounds
python main.py --kb --domain DOMAIN             # View KB status

# Crawl/RAG
python main.py --crawl URL --domain D           # Crawl docs
python main.py --crawl-inject --domain D        # Inject to KB
python main.py --rag-search "query"             # Search RAG

# Task Generation
python main.py --next-task --domain D           # Generate tasks
python main.py --auto-build --domain D          # Execute top task

# Vault
python main.py --vault-store KEY 'VALUE'        # Store credential
python main.py --vault-list                     # List keys

# Status
python main.py --status --domain D              # Strategy status
python main.py --budget                         # Cost tracking
```
