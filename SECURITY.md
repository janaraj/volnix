# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Volnix, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, use [GitHub's private vulnerability reporting](https://github.com/janaraj/volnix/security/advisories/new) to submit your report. This ensures the issue is handled confidentially.

### What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

### Response timeline

- **Acknowledgment:** within 48 hours
- **Initial assessment:** within 1 week
- **Fix or mitigation:** depends on severity, but we aim for 30 days for critical issues

## Scope

The following components are in scope:

- Core engine (state, policy, permission, budget, pipeline)
- HTTP API server and WebSocket endpoints
- MCP server adapter
- Persistence layer (SQLite, ledger, event bus)
- LLM router and secret resolution
- CLI commands that modify system state

Out of scope:

- The React dashboard (client-side only, no server-side rendering)
- Third-party dependencies (report those to the upstream project)

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

Only the latest release receives security patches.
