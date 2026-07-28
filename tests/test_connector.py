"""Connector tests, with a focus on credentials not escaping.

`--env` carries API tokens for real servers. These tests pin the places a
secret could plausibly reach — a repr, an error message, the snapshot on disk —
because each of those was, or nearly was, a real leak.
"""

from __future__ import annotations

import json

import pytest
import typer

from mcplock import store
from mcplock.cli import parse_env, resolve_target
from mcplock.connector import ServerTarget, derive_server_id

SECRET = "sk-CANARY-1a2b3c4d5e6f"


@pytest.fixture
def target_with_secret() -> ServerTarget:
    return ServerTarget.from_command("some-server --flag", env={"API_TOKEN": SECRET})


class TestSecretsDoNotEscape:
    def test_repr_redacts_env_values(self, target_with_secret: ServerTarget) -> None:
        rendered = repr(target_with_secret)

        assert SECRET not in rendered
        assert "API_TOKEN=<redacted>" in rendered

    def test_str_redacts_env_values(self, target_with_secret: ServerTarget) -> None:
        assert SECRET not in str(target_with_secret)

    def test_format_string_redacts_env_values(self, target_with_secret: ServerTarget) -> None:
        """The realistic leak: someone writes f-string logging in a later phase."""
        assert SECRET not in f"failed to reach {target_with_secret}"

    def test_secret_is_not_written_to_the_snapshot(
        self, target_with_secret: ServerTarget
    ) -> None:
        tools = [{"name": "t", "description": "d", "inputSchema": {"type": "object"}}]
        document = store.build_snapshot(target_with_secret, tools)
        path = store.save(document)

        assert SECRET not in json.dumps(document)
        assert SECRET not in path.read_text(encoding="utf-8")

    def test_malformed_env_error_does_not_echo_the_value(self) -> None:
        """A pasted secret missing its '=' must not land in the terminal."""
        with pytest.raises(typer.BadParameter) as excinfo:
            parse_env([SECRET])

        assert SECRET not in str(excinfo.value)
        assert "#1" in str(excinfo.value)

    def test_env_values_still_reach_the_server(self, target_with_secret: ServerTarget) -> None:
        """Redaction must not break the actual passthrough."""
        assert target_with_secret.env_dict() == {"API_TOKEN": SECRET}


class TestEnvFrom:
    def test_forwards_by_name_without_putting_the_value_in_argv(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", SECRET)

        target = resolve_target("some-server", "stdio", env=None, env_from=["GITHUB_TOKEN"])

        assert target.env_dict() == {"GITHUB_TOKEN": SECRET}

    def test_missing_variable_is_a_clear_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NOT_SET_ANYWHERE", raising=False)

        with pytest.raises(typer.BadParameter, match="NOT_SET_ANYWHERE"):
            parse_env(None, ["NOT_SET_ANYWHERE"])

    def test_env_and_env_from_merge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FROM_ENV", "b")

        assert parse_env(["INLINE=a"], ["FROM_ENV"]) == {"INLINE": "a", "FROM_ENV": "b"}

    def test_rejected_for_http_targets(self) -> None:
        with pytest.raises(typer.BadParameter, match="stdio"):
            resolve_target("https://example.test/mcp", "auto", env=["A=b"])


class TestCommandParsing:
    def test_strips_quotes_around_a_spaced_path(self) -> None:
        target = ServerTarget.from_command(r'"C:\Program Files\node.exe" server.js')

        assert target.command == r"C:\Program Files\node.exe"
        assert target.args == ("server.js",)

    def test_keeps_windows_backslashes(self) -> None:
        target = ServerTarget.from_command(r"npx server C:\data\notes")

        assert target.args == ("server", r"C:\data\notes")

    def test_rejects_an_empty_command(self) -> None:
        with pytest.raises(ValueError, match="empty server command"):
            ServerTarget.from_command("   ")

    def test_env_does_not_change_server_identity(self) -> None:
        """A rotated credential must not read as a different server."""
        plain = ServerTarget.from_command("some-server --flag")
        with_secret = ServerTarget.from_command("some-server --flag", env={"API_TOKEN": SECRET})

        assert plain.server_id == with_secret.server_id

    def test_server_id_is_filesystem_safe(self) -> None:
        server_id = derive_server_id("npx -y @scope/server https://x.test/a?b=c")

        assert not set(server_id) & set('<>:"/\\|?*')


class TestTransportInference:
    @pytest.mark.parametrize("url", ["http://x.test/mcp", "https://x.test/mcp"])
    def test_urls_infer_http(self, url: str) -> None:
        assert resolve_target(url, "auto").transport == "http"

    def test_commands_infer_stdio(self) -> None:
        assert resolve_target("npx -y server", "auto").transport == "stdio"

    def test_unknown_transport_is_rejected(self) -> None:
        with pytest.raises(typer.BadParameter, match="unsupported transport"):
            resolve_target("npx -y server", "carrier-pigeon")
