# FailWatch

**The Missing Safety Layer for AI Agents.**
FailWatch prevents your Agents from performing dangerous actions (e.g., unauthorized refunds, hallucinations, logic drift) by intercepting tool calls before they happen.

## Features
- **Deterministic Policy Checks**: Hard block on numeric limits.
- **Fail-Closed**: Financial-grade safety; if the guard is down, the money stays put.
- **Human-in-the-Loop**: Seamlessly escalate risky actions to Slack/CLI.

## Quick Start

1. Start Server:
   ```bash
   cd server
   export OPENAI_API_KEY=sk-...
   uvicorn main:app --reload