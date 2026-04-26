"""Subsystem clients — Python-side logic mirroring the agent prompts.

Each subsystem exposes a pure-Python class so:
- the daemon can drive them on cron schedules without spawning a CC agent
- tests can exercise the logic with mocks
- the agent .md prompts call into them via Bash tool when running in CC

Real Gmail/Calendar/Slack/etc. calls live behind provider-shaped interfaces
to keep tests deterministic and let us swap mock→MCP→direct API freely.
"""
