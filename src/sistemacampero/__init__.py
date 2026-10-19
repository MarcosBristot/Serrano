"""Sistema Campero: hub de telemetria agrícola multimarca."""


def main() -> None:
    """Ponto de entrada do console script (delega para a CLI)."""
    from sistemacampero.interfaces.cli import main as cli_main

    raise SystemExit(cli_main())
