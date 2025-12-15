"""Generate secure random keys for the application."""

import secrets
from collections.abc import Callable
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def hex_key(bytes_len: int) -> str:
    """Return a cryptographically secure random hex string of length 2 * bytes_len."""
    return secrets.token_hex(bytes_len)


def urlsafe_b64_key(bytes_len: int) -> str:
    """Return a URL-safe base64 key generated from random bytes (without padding)."""
    return secrets.token_urlsafe(bytes_len)


@dataclass(frozen=True)
class Secret:
    """Definition for a named secret and how to generate it."""

    name: str
    generator: Callable[[], str]
    notes: str


SECRETS: list[Secret] = [
    Secret(
        name="POSTGRES_PASSWORD",
        generator=lambda: hex_key(32),
        notes="64 hex chars (32 bytes)",
    ),
    Secret(
        name="JWT_SECRET_KEY",
        generator=lambda: urlsafe_b64_key(32),
        notes="JWT signing key (URL-safe)",
    ),
    Secret(
        name="ENCRYPTION_KEY",
        generator=lambda: hex_key(32),
        notes="64 hex chars (32 bytes)",
    ),
]


def render_secrets(secrets: list[Secret]) -> None:
    """Render the provided secrets as a Rich table suitable for copying into `.env`."""
    table = Table(
        title="Generated secrets for .env",
        show_lines=False,
        header_style="bold cyan",
        box=None,
    )

    table.add_column("Variable", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")
    table.add_column("Notes", style="dim")

    for secret in secrets:
        table.add_row(
            secret.name,
            secret.generator(),
            secret.notes,
        )

    console.print(Panel(table, padding=(1, 2)))


def main() -> None:
    """CLI entrypoint."""
    render_secrets(SECRETS)


if __name__ == "__main__":
    main()
