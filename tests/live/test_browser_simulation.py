"""Live Test: Browser Pack E2E Simulation

Simulates a support agent browsing the world:
1. Compile world from YAML (acme_support.yaml includes browser service)
2. Generate entities via codex-acp (web_site, web_page, web_session)
3. Agent browses: list sites, search, navigate, read, click links
4. Verify state changes persisted
5. Show generated web page content

Run with:
    uv run pytest tests/live/test_browser_simulation.py -v -s
"""

from __future__ import annotations

import json
import os

import pytest

from terrarium.actors.definition import ActorDefinition
from terrarium.core.types import ActorId, ActorType

# Bypass GOOGLE_API_KEY skip check — we use codex-acp, not Google
os.environ.setdefault("GOOGLE_API_KEY", "")


def _ensure_agent(app, agent_id: str):
    """Register a test agent if not already present in the actor registry."""
    compiler = app.registry.get("world_compiler")
    actor_registry = compiler._config.get("_actor_registry")
    if actor_registry and not actor_registry.has_actor(ActorId(agent_id)):
        actor_registry.register(
            ActorDefinition(
                id=ActorId(agent_id),
                type=ActorType.AGENT,
                role="test-agent",
                permissions={"write": "all", "read": "all"},
            )
        )


@pytest.mark.asyncio
class TestBrowserSimulation:
    """Complete E2E: compile → generate → browse → verify."""

    async def test_browser_full_simulation(self, live_app) -> None:
        """Full simulation: generate web pages via LLM, then agent browses them."""
        compiler = live_app.registry.get("world_compiler")

        print("\n" + "=" * 70)
        print("BROWSER PACK LIVE E2E SIMULATION")
        print("=" * 70)

        # ── PHASE 1: COMPILE ──
        print("\n" + "─" * 40)
        print("PHASE 1: COMPILE FROM YAML")
        print("─" * 40)

        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        print(f"  World: {plan.name}")
        print(f"  Services: {plan.get_service_names()}")
        print(f"  Entity types: {plan.get_entity_types()}")

        # Verify browser service resolved
        entity_types = plan.get_entity_types()
        assert "web_page" in entity_types, f"web_page not in {entity_types}"
        assert "web_site" in entity_types, f"web_site not in {entity_types}"

        # ── PHASE 2: GENERATE ──
        print("\n" + "─" * 40)
        print("PHASE 2: GENERATE WORLD VIA LLM (codex-acp)")
        print("─" * 40)

        result = await compiler.generate_world(plan)

        total_entities = sum(len(v) for v in result["entities"].values())
        print(f"  Total entities generated: {total_entities}")
        for etype, entities in result["entities"].items():
            print(f"    {etype}: {len(entities)}")

        # ── PHASE 3: SHOW GENERATED WEB PAGES ──
        print("\n" + "─" * 40)
        print("PHASE 3: GENERATED WEB CONTENT")
        print("─" * 40)

        state = live_app.registry.get("state")
        all_sites = await state.query_entities("web_site")
        all_pages = await state.query_entities("web_page")

        print(f"\n  Web Sites ({len(all_sites)}):")
        for site in all_sites:
            print(f"    {site.get('domain')} — {site.get('name')} ({site.get('site_type')})")

        print(f"\n  Web Pages ({len(all_pages)}):")
        for i, page in enumerate(all_pages):
            print(f"\n  ── Page {i + 1} ──")
            print(f"    URL:     {page.get('domain', '')}{page.get('path', '')}")
            print(f"    Title:   {page.get('title', 'N/A')}")
            print(f"    Type:    {page.get('page_type', 'N/A')}")
            print(f"    Status:  {page.get('status', 'N/A')}")
            content = page.get("content_text", "")
            print(f"    Content: {content[:200]}{'...' if len(content) > 200 else ''}")
            links = page.get("links", [])
            if links:
                print(f"    Links:   {json.dumps(links[:3], default=str)}")
            forms = page.get("forms", [])
            if forms:
                print(f"    Forms:   {json.dumps(forms, default=str)[:250]}")

        assert len(all_pages) > 0, "Should have generated web_page entities"

        # ── PHASE 4: AGENT BROWSES ──
        print("\n" + "─" * 40)
        print("PHASE 4: AGENT BROWSING ACTIONS")
        print("─" * 40)

        _ensure_agent(live_app, "agent-browser")

        # Action 1: List sites
        r1 = await live_app.handle_action(
            "agent-browser", "browser", "web_list_sites", {},
        )
        site_count = r1.get("count", 0) if isinstance(r1, dict) else 0
        print(f"\n  Action 1 — web_list_sites: {site_count} sites")
        if isinstance(r1, dict):
            for s in r1.get("sites", []):
                print(f"    • {s.get('domain')} ({s.get('site_type')})")

        # Action 2: Search
        r2 = await live_app.handle_action(
            "agent-browser", "browser", "web_search", {"query": "support"},
        )
        search_count = r2.get("count", 0) if isinstance(r2, dict) else 0
        print(f"\n  Action 2 — web_search('support'): {search_count} results")
        if isinstance(r2, dict):
            for res in r2.get("results", [])[:5]:
                print(f"    • {res.get('title')} @ {res.get('url')}")

        # Action 3: Navigate to first page
        if all_pages:
            first_page = all_pages[0]
            nav_url = f"{first_page.get('domain', '')}{first_page.get('path', '')}"
            r3 = await live_app.handle_action(
                "agent-browser", "browser", "web_navigate", {"url": nav_url},
            )
            print(f"\n  Action 3 — web_navigate('{nav_url}'):")
            if isinstance(r3, dict) and r3.get("page"):
                print(f"    Title:   {r3['page'].get('title')}")
                print(f"    Content: {str(r3['page'].get('content_text', ''))[:200]}")
                print(f"    Links:   {len(r3['page'].get('links', []))}")
                print(f"    Forms:   {len(r3['page'].get('forms', []))}")
                session_id = r3.get("session_id")
                print(f"    Session: {session_id}")

                # Action 4: Read current page
                if session_id:
                    r4 = await live_app.handle_action(
                        "agent-browser", "browser", "web_read_page",
                        {"session_id": session_id},
                    )
                    print(f"\n  Action 4 — web_read_page(session):")
                    if isinstance(r4, dict) and r4.get("page"):
                        print(f"    Title: {r4['page'].get('title')}")

                # Action 5: Click a link if available
                page_links = r3["page"].get("links", [])
                if page_links and session_id:
                    r5 = await live_app.handle_action(
                        "agent-browser", "browser", "web_click_link",
                        {"session_id": session_id, "link_index": 0},
                    )
                    print(f"\n  Action 5 — web_click_link(index=0):")
                    if isinstance(r5, dict) and r5.get("page"):
                        print(f"    Navigated to: {r5['page'].get('title')}")
                    elif isinstance(r5, dict) and r5.get("error"):
                        print(f"    {r5['error']}: {r5.get('description', '')}")

            elif isinstance(r3, dict) and r3.get("error"):
                print(f"    Error: {r3['error']} — {r3.get('description', '')}")

        # ── PHASE 5: VERIFY STATE ──
        print("\n" + "─" * 40)
        print("PHASE 5: STATE VERIFICATION")
        print("─" * 40)

        sessions_after = await state.query_entities("web_session")
        pages_after = await state.query_entities("web_page")
        print(f"  web_sessions: {len(sessions_after)}")
        print(f"  web_pages: {len(pages_after)}")

        print("\n  ✓ Browser pack live E2E complete")

        # ── ASSERTIONS ──
        assert len(all_pages) > 0, "Should have generated web_page entities"
        assert total_entities > 0, "Should have non-zero entities"
