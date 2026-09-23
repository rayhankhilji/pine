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
def version() -> None:
    """Print the Pine version."""
    console.print(f"pine {__version__}")


if __name__ == "__main__":
    app()
