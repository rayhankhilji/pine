import asyncio

import typer
import uvicorn
from rich.console import Console

from pine import __version__

app = typer.Typer(name="pine", help="Pine — Private Markets Intelligence Engine")
console = Console()


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Run the Pine API server."""
    uvicorn.run("pine.main:app", host=host, port=port, reload=reload)


@app.command()
def worker() -> None:
    """Run the background job worker standalone."""
    import pine.index.jobs  # noqa: F401 — registers job handlers
    import pine.ingest.jobs  # noqa: F401 — registers job handlers
    from pine.config import get_settings
    from pine.db import SessionLocal
    from pine.jobs.worker import Worker
    from pine.logging import configure_logging

    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    w = Worker(SessionLocal, concurrency=settings.WORKER_CONCURRENCY)
    console.print(f"[green]worker[/green] {w.worker_id} polling…")
    try:
        asyncio.run(w.run_forever())
    except KeyboardInterrupt:
        w.stop()


demo_app = typer.Typer(help="Demo data room commands")
app.add_typer(demo_app, name="demo")


@demo_app.command("build")
def demo_build(
    out: str = "fixtures/northwind",
    force: bool = False,
) -> None:
    """Build the synthetic Northwind data room (F-14)."""
    from pine.demo.build import build_demo

    try:
        path = build_demo(out, force=force)
    except FileExistsError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    n = sum(1 for p in path.rglob("*") if p.is_file())
    console.print(f"[green]demo room built[/green] {path} ({n} files)")


@app.command()
def version() -> None:
    """Print the Pine version."""
    console.print(f"pine {__version__}")


if __name__ == "__main__":
    app()
