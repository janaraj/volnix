"""Tests for volnix.config.loader — config loading, merging, and env overrides."""

from pathlib import Path

import pytest

from volnix.config.loader import ConfigLoader


def test_load_base_config(tmp_path: Path):
    """Loading a base volnix.toml produces a valid config."""
    toml_file = tmp_path / "volnix.toml"
    toml_file.write_text('[simulation]\nseed = 100\nmode = "governed"\n')
    loader = ConfigLoader(base_dir=tmp_path)
    config = loader.load()
    assert config.simulation.seed == 100
    assert config.simulation.mode == "governed"


def test_load_with_env_override(tmp_path: Path):
    """Environment-specific TOML overrides base values."""
    base = tmp_path / "volnix.toml"
    base.write_text('[simulation]\nseed = 42\nmode = "governed"\n')
    env_file = tmp_path / "volnix.development.toml"
    env_file.write_text("[simulation]\nseed = 99\n")
    loader = ConfigLoader(base_dir=tmp_path, env="development")
    config = loader.load()
    assert config.simulation.seed == 99
    # mode should still be governed from base
    assert config.simulation.mode == "governed"


def test_load_with_local_override(tmp_path: Path):
    """Local TOML overrides both base and env values."""
    base = tmp_path / "volnix.toml"
    base.write_text('[simulation]\nseed = 42\nmode = "governed"\n')
    env_file = tmp_path / "volnix.development.toml"
    env_file.write_text("[simulation]\nseed = 99\n")
    local_file = tmp_path / "volnix.local.toml"
    local_file.write_text("[simulation]\nseed = 7\n")
    loader = ConfigLoader(base_dir=tmp_path, env="development")
    config = loader.load()
    assert config.simulation.seed == 7


def test_env_var_override(monkeypatch, tmp_path: Path):
    """VOLNIX__SIMULATION__SEED env var overrides TOML value."""
    base = tmp_path / "volnix.toml"
    base.write_text("[simulation]\nseed = 42\n")
    monkeypatch.setenv("VOLNIX__SIMULATION__SEED", "99")
    loader = ConfigLoader(base_dir=tmp_path)
    config = loader.load()
    assert config.simulation.seed == 99


def test_resolve_secure_refs(monkeypatch, tmp_path: Path):
    """Secure *_ref fields are resolved from environment variables."""
    base = tmp_path / "volnix.toml"
    base.write_text(
        '[llm.providers.anthropic]\ntype = "anthropic"\napi_key_ref = "MY_SECRET_KEY"\n'
    )
    monkeypatch.setenv("MY_SECRET_KEY", "sk-test-12345")
    loader = ConfigLoader(base_dir=tmp_path)
    config = loader.load()
    provider = config.llm.providers["anthropic"]
    assert provider.api_key_ref == "MY_SECRET_KEY"


def test_deep_merge_nested():
    """Nested dicts are merged recursively, not replaced."""
    base = {"simulation": {"seed": 42, "mode": "governed"}, "bus": {"db_path": "a.db"}}
    override = {"simulation": {"seed": 99}}
    result = ConfigLoader._deep_merge(base, override)
    assert result["simulation"]["seed"] == 99
    assert result["simulation"]["mode"] == "governed"
    assert result["bus"]["db_path"] == "a.db"


def test_deep_merge_override():
    """Scalar values in override win over base."""
    base = {"a": 1, "b": 2}
    override = {"b": 99}
    result = ConfigLoader._deep_merge(base, override)
    assert result["a"] == 1
    assert result["b"] == 99


def test_missing_toml_returns_defaults(tmp_path: Path):
    """An empty directory with no TOML files produces default VolnixConfig."""
    loader = ConfigLoader(base_dir=tmp_path)
    config = loader.load()
    assert config.simulation.mode == "governed"
    assert config.simulation.seed == 42


def test_coerce_types():
    """String coercion handles booleans, ints, floats, and strings."""
    assert ConfigLoader._coerce("true") is True
    assert ConfigLoader._coerce("false") is False
    assert ConfigLoader._coerce("42") == 42
    assert ConfigLoader._coerce("3.14") == pytest.approx(3.14)
    assert ConfigLoader._coerce("hello") == "hello"
    assert ConfigLoader._coerce("yes") is True
    assert ConfigLoader._coerce("no") is False
    assert ConfigLoader._coerce("0") == 0  # "0" coerces to int, not bool
    assert ConfigLoader._coerce("1") == 1  # "1" coerces to int, not bool


def test_malformed_toml(tmp_path: Path):
    """Invalid TOML raises an error during loading."""
    bad_file = tmp_path / "volnix.toml"
    bad_file.write_text("this is not valid [[ toml")
    loader = ConfigLoader(base_dir=tmp_path)
    with pytest.raises(Exception):
        loader.load()


def test_nonexistent_base_dir(tmp_path: Path):
    """A missing base directory produces default VolnixConfig."""
    missing_dir = tmp_path / "does_not_exist"
    loader = ConfigLoader(base_dir=missing_dir)
    config = loader.load()
    assert config.simulation.seed == 42


def test_env_var_nested_override(monkeypatch, tmp_path: Path):
    """Deeply nested env var override works."""
    base = tmp_path / "volnix.toml"
    base.write_text("")
    monkeypatch.setenv("VOLNIX__BUDGET__WARNING_THRESHOLD_PCT", "90")
    loader = ConfigLoader(base_dir=tmp_path)
    config = loader.load()
    assert config.budget.warning_threshold_pct == 90.0


def test_secure_ref_missing_env_var(tmp_path: Path):
    """Missing env var for a *_ref leaves the ref string as-is."""
    base = tmp_path / "volnix.toml"
    base.write_text(
        '[llm.providers.anthropic]\ntype = "anthropic"\napi_key_ref = "NONEXISTENT_SECRET_KEY"\n'
    )
    loader = ConfigLoader(base_dir=tmp_path)
    config = loader.load()
    provider = config.llm.providers["anthropic"]
    assert provider.api_key_ref == "NONEXISTENT_SECRET_KEY"


def test_load_real_volnix_toml():
    """Loading the actual volnix.toml from the repo root succeeds."""
    repo_root = Path(__file__).resolve().parents[2]
    loader = ConfigLoader(base_dir=repo_root, env="__nonexistent__")
    config = loader.load()
    assert config.simulation.mode == "governed"
    assert config.simulation.seed == 42
    assert len(config.pipeline.steps) >= 1
