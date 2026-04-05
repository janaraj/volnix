"""Webhook event delivery — push simulated service events to agent endpoints.

Subscribes to the event bus and delivers matching events via HTTP POST
to registered webhook URLs. Simulates real service webhooks (Gmail Pub/Sub,
Slack Events API, Stripe webhooks, etc.).

Disabled by default. Enable in volnix.toml: ``[webhook] enabled = true``
"""
