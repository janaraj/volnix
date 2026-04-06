"""Web Dashboard -- live monitoring, replay, and report viewing.

This package provides a FastAPI-based web dashboard for observing
running worlds, replaying completed runs, and viewing evaluation
reports.
"""

from volnix.dashboard.app import create_app

__all__ = ["create_app"]
