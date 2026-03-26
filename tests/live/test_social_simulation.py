"""Live E2E test: Social Media world with Reddit + Twitter packs.

Creates a social media monitoring world where:
- A brand has presence on Reddit (r/AcmeSupport) and Twitter (@AcmeSupport)
- Customers post complaints and questions on both platforms
- A support agent monitors, responds, and engages
- Animator generates organic social activity (new posts, replies, votes)

Requires: codex-acp binary available (uses terrarium.toml routing)

Run with:
    uv run pytest tests/live/test_social_simulation.py -v -s
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta

import pytest

from terrarium.core.types import RunId


@pytest.fixture
async def social_app(tmp_path):
    """TerrariumApp with codex-acp for social media simulation."""
    if not shutil.which("codex-acp"):
        pytest.skip("codex-acp not found — skipping live test")

    from terrarium.app import TerrariumApp
    from terrarium.config.loader import ConfigLoader
    from terrarium.engines.state.config import StateConfig
    from terrarium.persistence.config import PersistenceConfig

    loader = ConfigLoader()
    config = loader.load()
    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })

    app = TerrariumApp(config)
    await app.start()
    yield app
    await app.stop()


class TestSocialMediaSimulation:
    """Full lifecycle: compile → generate → browse → post → engage → animate → report."""

    @pytest.mark.asyncio
    async def test_reddit_twitter_simulation(self, social_app) -> None:
        """E2E simulation of social media monitoring and engagement."""
        app = social_app
        compiler = app.registry.get("world_compiler")

        # ────────────────────────────────────────────────────
        # STEP 1: Build world plan with Reddit + Twitter
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 1: BUILD SOCIAL MEDIA WORLD PLAN")
        print("=" * 70)

        from terrarium.engines.world_compiler.plan import (
            ServiceResolution,
            WorldPlan,
        )
        from terrarium.kernel.surface import ServiceSurface
        from terrarium.packs.verified.reddit.pack import RedditPack
        from terrarium.packs.verified.twitter.pack import TwitterPack
        from terrarium.reality.presets import load_preset

        reddit_surface = ServiceSurface.from_pack(RedditPack())
        twitter_surface = ServiceSurface.from_pack(TwitterPack())

        plan = WorldPlan(
            name="Acme Social Media Operations",
            description=(
                "Acme Corp runs customer support and marketing through "
                "Reddit (r/AcmeSupport, r/AcmeTech) and Twitter (@AcmeSupport). "
                "The team monitors for complaints, responds to questions, "
                "and engages with the community. Some customers are frustrated "
                "about a recent outage."
            ),
            seed=42,
            behavior="dynamic",
            mode="governed",
            services={
                "reddit": ServiceResolution(
                    service_name="reddit",
                    spec_reference="verified/reddit",
                    surface=reddit_surface,
                    resolution_source="tier1_pack",
                ),
                "twitter": ServiceResolution(
                    service_name="twitter",
                    spec_reference="verified/twitter",
                    surface=twitter_surface,
                    resolution_source="tier1_pack",
                ),
            },
            actor_specs=[
                {
                    "role": "social-media-agent",
                    "type": "external",
                    "count": 1,
                    "personality": "Brand-aware, empathetic, professional",
                },
                {
                    "role": "community-manager",
                    "type": "internal",
                    "count": 1,
                    "personality": (
                        "Experienced community moderator who keeps discussions "
                        "civil and escalates serious complaints."
                    ),
                },
            ],
            conditions=load_preset("messy"),
            reality_prompt_context={},
            policies=[
                {
                    "name": "Public response policy",
                    "description": "All public responses must be professional",
                    "trigger": "social media post or reply",
                    "enforcement": "log",
                },
                {
                    "name": "Escalation policy",
                    "description": (
                        "Posts with 10+ negative engagement require "
                        "immediate escalation"
                    ),
                    "trigger": "post score drops below -10",
                    "enforcement": "escalate",
                },
            ],
            seeds=[
                (
                    "Customer @angry_user tweeted: 'Been down for 3 hours, "
                    "no response from @AcmeSupport. Worst service ever.'"
                ),
                (
                    "Reddit post in r/AcmeSupport: 'Outage affecting "
                    "production — anyone else seeing this?'"
                ),
                (
                    "Several customers are praising Acme's new feature "
                    "launch on both platforms"
                ),
            ],
            mission=(
                "Monitor social media for customer issues. Respond to "
                "complaints within policy. Engage positively with the community."
            ),
        )

        print(f"  World: {plan.name}")
        print(f"  Services: {list(plan.services.keys())}")
        print(f"  Behavior: {plan.behavior}")
        print(f"  Mode: {plan.mode}")
        print(f"  Seeds: {len(plan.seeds)} scenarios")

        # ────────────────────────────────────────────────────
        # STEP 2: Generate world with REAL LLM
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 2: GENERATE WORLD (codex-acp)")
        print("=" * 70)

        result = await compiler.generate_world(plan)

        entity_summary = {
            etype: len(elist) for etype, elist in result["entities"].items()
        }
        total_entities = sum(entity_summary.values())
        print(f"  Generated entities: {json.dumps(entity_summary, indent=4)}")
        print(f"  Total: {total_entities} entities")
        print(f"  Actors: {len(result['actors'])}")

        # Verify social entities were generated
        assert total_entities > 0, "No entities generated"

        # Show sample entities
        for etype, elist in result["entities"].items():
            if elist:
                sample = elist[0]
                fields = list(sample.keys())[:6]
                print(
                    f"\n  Sample {etype}: "
                    f"{json.dumps({k: sample.get(k) for k in fields}, default=str)}"
                )

        # ────────────────────────────────────────────────────
        # STEP 3: Configure governance + animator
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 3: CONFIGURE GOVERNANCE + ANIMATOR")
        print("=" * 70)

        app.configure_governance(plan)
        await app.configure_animator(plan)
        print("  Governance: configured (governed mode)")
        print("  Animator: configured (dynamic mode)")

        # ────────────────────────────────────────────────────
        # STEP 4: Agent actions — Reddit
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 4: AGENT ACTIONS — REDDIT")
        print("=" * 70)

        actors = result["actors"]
        agent_actor = next(
            (a for a in actors if a.role == "social-media-agent"),
            actors[0],
        )
        agent_id = str(agent_actor.id)
        print(f"  Using actor: {agent_id} (role={agent_actor.role})")

        state_engine = app.registry.get("state")

        # 4a: Browse subreddits
        subreddits = await state_engine.query_entities("subreddit")
        if subreddits:
            sr = subreddits[0]
            sr_name = sr.get("name", "AcmeSupport")
            print(f"\n  4a. Browsing r/{sr_name}...")

            r_hot = await app.handle_action(
                agent_id, "reddit", "reddit_subreddit_hot",
                {"subreddit": sr_name, "limit": 5},
            )
            hot_posts = r_hot.get("data", {}).get("children", [])
            print(f"      Hot posts: {len(hot_posts)}")
            for p in hot_posts[:3]:
                pdata = p.get("data", p) if isinstance(p, dict) else p
                print(
                    f"        [{pdata.get('score', 0)}] "
                    f"{pdata.get('title', 'untitled')[:60]}"
                )

        # 4b: Agent submits a post
        print("\n  4b. Agent posts a response thread...")
        r_submit = await app.handle_action(
            agent_id, "reddit", "reddit_submit",
            {
                "sr": sr_name if subreddits else "AcmeSupport",
                "title": "Official Response: Service Outage Update",
                "text": (
                    "Hi everyone, we're aware of the outage affecting "
                    "some users. Our engineering team is actively working "
                    "on a fix. We'll update this thread as we make progress."
                ),
                "kind": "text",
                "author_id": agent_id,
            },
        )
        post_id = r_submit.get("data", {}).get("id", "")
        print(f"      Post created: {post_id}")
        print(f"      Response: {json.dumps(r_submit, default=str)[:200]}")

        # 4c: Agent comments on an existing post
        reddit_posts = await state_engine.query_entities("reddit_post")
        if reddit_posts:
            target_post = reddit_posts[0]
            target_id = target_post.get("id", "")
            print(f"\n  4c. Replying to post: {target_id}...")
            r_comment = await app.handle_action(
                agent_id, "reddit", "reddit_comment",
                {
                    "parent": target_id,
                    "text": (
                        "Thanks for reporting this. We're looking into "
                        "it right now."
                    ),
                    "author_id": agent_id,
                },
            )
            print(
                f"      Comment: "
                f"{json.dumps(r_comment, default=str)[:200]}"
            )

        # 4d: Agent upvotes a community post
        if reddit_posts and len(reddit_posts) > 1:
            vote_target = reddit_posts[1]
            print(f"\n  4d. Upvoting post: {vote_target.get('id')}...")
            r_vote = await app.handle_action(
                agent_id, "reddit", "reddit_vote",
                {
                    "id": vote_target["id"],
                    "dir": 1,
                    "user_id": agent_id,
                },
            )
            print(f"      Vote result: {json.dumps(r_vote, default=str)[:150]}")

        # ────────────────────────────────────────────────────
        # STEP 5: Agent actions — Twitter
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 5: AGENT ACTIONS — TWITTER")
        print("=" * 70)

        # 5a: Agent tweets
        print("  5a. Posting tweet about outage update...")
        r_tweet = await app.handle_action(
            agent_id, "twitter", "twitter_create_tweet",
            {
                "text": (
                    "We're aware of the service disruption and our team "
                    "is working on a fix. Follow this thread for updates. "
                    "#AcmeStatus #ServiceUpdate"
                ),
                "author_id": agent_id,
            },
        )
        tweet_id = r_tweet.get("data", {}).get("id", "")
        print(f"      Tweet: {tweet_id}")
        print(f"      Response: {json.dumps(r_tweet, default=str)[:200]}")

        # 5b: Search for customer complaints
        print("\n  5b. Searching for complaints...")
        r_search = await app.handle_action(
            agent_id, "twitter", "twitter_search_recent",
            {"query": "#AcmeSupport", "max_results": 5},
        )
        search_results = r_search.get("data", [])
        print(f"      Found {len(search_results)} tweets matching #AcmeSupport")

        # 5c: Reply to a customer complaint
        tweets = await state_engine.query_entities("tweet")
        complaint_tweets = [
            t for t in tweets
            if t.get("author_id") != agent_id
            and t.get("status") == "published"
        ]
        if complaint_tweets:
            complaint = complaint_tweets[0]
            print(
                f"\n  5c. Replying to complaint tweet: "
                f"{complaint.get('id')}..."
            )
            r_reply = await app.handle_action(
                agent_id, "twitter", "twitter_reply",
                {
                    "text": (
                        "We're sorry for the inconvenience. Our team is "
                        "actively investigating. Can you DM us your "
                        "account details so we can help?"
                    ),
                    "author_id": agent_id,
                    "in_reply_to_tweet_id": complaint["id"],
                },
            )
            print(
                f"      Reply: {json.dumps(r_reply, default=str)[:200]}"
            )

        # 5d: Like a positive tweet
        positive_tweets = [
            t for t in tweets
            if t.get("like_count", 0) > 0
            and t.get("status") == "published"
        ]
        if positive_tweets:
            target = positive_tweets[0]
            print(f"\n  5d. Liking tweet: {target.get('id')}...")
            r_like = await app.handle_action(
                agent_id, "twitter", "twitter_like",
                {"user_id": agent_id, "tweet_id": target["id"]},
            )
            print(f"      Like: {json.dumps(r_like, default=str)[:150]}")

        # ────────────────────────────────────────────────────
        # STEP 6: Animator ticks (dynamic mode)
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 6: ANIMATOR TICKS (dynamic mode)")
        print("=" * 70)

        animator = app.registry.get("animator")
        now = datetime.now(UTC)

        for tick in range(3):
            tick_time = now + timedelta(minutes=tick * 5)
            results = await animator.tick(tick_time)
            print(f"\n  Tick {tick + 1}: {len(results)} events generated")
            for evt in results[:3]:
                print(
                    f"    → {json.dumps(evt, default=str)[:150]}"
                )

        # ────────────────────────────────────────────────────
        # STEP 7: Query final state
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 7: FINAL STATE")
        print("=" * 70)

        # Reddit state
        for etype in ["subreddit", "reddit_post", "reddit_comment",
                       "reddit_user", "reddit_vote"]:
            entities = await state_engine.query_entities(etype)
            print(f"  {etype}: {len(entities)} entities")

        # Twitter state
        for etype in ["tweet", "twitter_user", "twitter_follow",
                       "twitter_like"]:
            entities = await state_engine.query_entities(etype)
            print(f"  {etype}: {len(entities)} entities")

        # ────────────────────────────────────────────────────
        # STEP 8: Report
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 8: GOVERNANCE REPORT")
        print("=" * 70)

        reporter = app.registry.get("reporter")
        if reporter:
            try:
                scorecard = await reporter.compute_scorecard(
                    await state_engine.get_event_log(),
                    plan,
                )
                print(f"  Scorecard: {json.dumps(scorecard, indent=4, default=str)[:500]}")
            except (AttributeError, Exception) as exc:
                print(f"  Scorecard: skipped ({exc})")

        # ── ASSERTIONS ──────────────────────────────────────
        print("\n" + "=" * 70)
        print("ASSERTIONS")
        print("=" * 70)

        assert total_entities > 0, "World should have entities"
        # Agent actions should have succeeded
        assert post_id or r_submit.get("data"), "Reddit post should have been created"
        assert tweet_id or r_tweet.get("data"), "Tweet should have been created"

        print("  ✅ All assertions passed")
        print(f"  Total entities at end: {total_entities}")
