"""Tests for terrarium.llm.secrets -- secret resolution for API keys."""

from terrarium.llm.secrets import (
    ChainResolver,
    EnvVarResolver,
    FileResolver,
    SecretResolver,
)


def test_env_var_resolver_found(monkeypatch):
    """EnvVarResolver returns the value when the env var exists."""
    monkeypatch.setenv("TEST_SECRET_KEY", "sk-12345")
    resolver = EnvVarResolver()
    assert resolver.resolve("TEST_SECRET_KEY") == "sk-12345"


def test_env_var_resolver_missing(monkeypatch):
    """EnvVarResolver returns None when the env var does not exist."""
    monkeypatch.delenv("NONEXISTENT_SECRET_KEY_XYZ", raising=False)
    resolver = EnvVarResolver()
    assert resolver.resolve("NONEXISTENT_SECRET_KEY_XYZ") is None


def test_file_resolver_found(tmp_path):
    """FileResolver returns file contents when the secret file exists."""
    secret_file = tmp_path / "MY_API_KEY"
    secret_file.write_text("  file-secret-value  \n")
    resolver = FileResolver(secrets_dir=str(tmp_path))
    assert resolver.resolve("MY_API_KEY") == "file-secret-value"


def test_file_resolver_missing(tmp_path):
    """FileResolver returns None when the secret file does not exist."""
    resolver = FileResolver(secrets_dir=str(tmp_path))
    assert resolver.resolve("NONEXISTENT_FILE") is None


def test_file_resolver_strips_whitespace(tmp_path):
    """FileResolver strips leading and trailing whitespace from file contents."""
    secret_file = tmp_path / "KEY"
    secret_file.write_text("\n  hello-world  \n\n")
    resolver = FileResolver(secrets_dir=str(tmp_path))
    assert resolver.resolve("KEY") == "hello-world"


def test_chain_resolver_first_wins(monkeypatch, tmp_path):
    """ChainResolver returns the value from the first resolver that hits."""
    monkeypatch.setenv("CHAINED_KEY", "from-env")
    secret_file = tmp_path / "CHAINED_KEY"
    secret_file.write_text("from-file")

    chain = ChainResolver([EnvVarResolver(), FileResolver(secrets_dir=str(tmp_path))])
    assert chain.resolve("CHAINED_KEY") == "from-env"


def test_chain_resolver_falls_through(monkeypatch, tmp_path):
    """ChainResolver falls through to the next resolver if the first misses."""
    monkeypatch.delenv("FALLBACK_KEY", raising=False)
    secret_file = tmp_path / "FALLBACK_KEY"
    secret_file.write_text("from-file")

    chain = ChainResolver([EnvVarResolver(), FileResolver(secrets_dir=str(tmp_path))])
    assert chain.resolve("FALLBACK_KEY") == "from-file"


def test_chain_resolver_all_miss(monkeypatch, tmp_path):
    """ChainResolver returns None when no resolver can find the secret."""
    monkeypatch.delenv("MISSING_EVERYWHERE", raising=False)
    chain = ChainResolver([EnvVarResolver(), FileResolver(secrets_dir=str(tmp_path))])
    assert chain.resolve("MISSING_EVERYWHERE") is None


def test_secret_resolver_protocol():
    """All resolvers satisfy the SecretResolver protocol."""
    assert isinstance(EnvVarResolver(), SecretResolver)
    assert isinstance(FileResolver(), SecretResolver)
    assert isinstance(ChainResolver(), SecretResolver)
