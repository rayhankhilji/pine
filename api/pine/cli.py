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


@app.command()
def version() -> None:
    """Print the Pine version."""
    console.print(f"pine {__version__}")


if __name__ == "__main__":
    app()
