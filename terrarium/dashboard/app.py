"""FastAPI application factory for the Terrarium dashboard.

Creates and configures the dashboard web application with live view,
replay, report, and API routes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DashboardConfig(BaseModel):
    """Configuration for the dashboard web application.

    Attributes:
        host: Bind address for the server.
        port: Port number for the server.
        debug: Whether to enable debug mode.
        static_dir: Path to static assets directory.
        template_dir: Path to HTML templates directory.
    """

    host: str = "127.0.0.1"
    port: int = 8080
    debug: bool = False
    static_dir: str = ""
    template_dir: str = ""


def create_app(config: DashboardConfig) -> object:
    """Create and return a configured FastAPI application.

    Args:
        config: Dashboard configuration settings.

    Returns:
        A FastAPI application instance with all routes mounted.
    """
    ...
