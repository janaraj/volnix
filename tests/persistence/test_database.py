"""Tests for volnix.persistence.database — abstract database interface."""
import pytest
from volnix.persistence.database import Database


def test_database_abc_cannot_instantiate():
    """Database is abstract and must not be instantiated directly."""
    with pytest.raises(TypeError):
        Database()  # type: ignore[abstract]
