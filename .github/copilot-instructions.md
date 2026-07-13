# CrewPilot — Copilot Instructions

This repository contains **CrewPilot**, an AI Engineering Intelligence Platform built as a GitHub Copilot custom agent.

## Quick Reference

- **Agent router**: `.github/agents/crewpilot.md` — the single source of truth for skill routing, role matrix, and guardrails
- **Skills**: `.github/skills/*/SKILL.md` — 16 structured methodology files across 5 pillars + 3 automation skills
- **MCP Server**: `crewpilot-engine/` (CrewPilot MCP server) — TypeScript MCP server with 55 tools across 8 modules + config

## How to Use

Type `@crewpilot` in GitHub Copilot Chat. The agent will ask for a session role (Build, Review, Plan, Design, or Just Ask), then route your requests to the appropriate skill.

## Key Conventions

- **Conventional commits**: `type(scope): message`
- **Human gates**: Autopilot always pauses for approval at critical points
- **Branch protection**: Never commit directly to `main`/`master`/`release/*`
- **Progressive disclosure**: Summaries first, details on request
- **Confidence gating**: Findings below threshold (default 7/10) are suppressed

## Configuration

`.github/crewpilot.config.json` controls thresholds, pillar toggles, and per-skill overrides. See `crewpilot_config_get` tool.

## Architecture

```
User → @crewpilot (router) → SKILL.md (methodology) → MCP tools (execution)
                                                      ↓
                                          SQLite (knowledge + workflows)
                                          gh CLI / az CLI / jira CLI (Board providers)
```

For full details, see the [README](../README.md) or the [agent definition](agents/crewpilot.md).
