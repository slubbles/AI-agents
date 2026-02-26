"""
VPS Deployment & Scheduler — Remote execution for Agent Brain.

Manages deployment to and scheduling on a VPS:

1. DEPLOY: Package Agent Brain → transfer to VPS → install deps → configure
2. SCHEDULE: Cron-based scheduling for autonomous runs
3. MONITOR: Health checks, log streaming, remote status
4. MANAGE: Start/stop/restart, rotate keys, update code

Supports SSH-based deployment (no cloud provider lock-in).
Vault stores SSH keys and VPS credentials.

IMPORTANT: This module builds deployment TOOLING. It does NOT actually
deploy to a VPS until the user explicitly triggers it.
"""
