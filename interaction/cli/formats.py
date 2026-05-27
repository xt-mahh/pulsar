from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

console = Console()


def print_success(message: str):
    rprint(f"[bold green]✓[/bold green] {message}")


def print_error(message: str):
    rprint(f"[bold red]✗[/bold red] {message}")


def print_info(message: str):
    rprint(f"[bold blue]ℹ[/bold blue] {message}")


def print_table(title: str, columns: list[str], rows: list[list]):
    table = Table(title=title)
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    console.print(table)


def print_panel(title: str, content: str):
    console.print(Panel(content, title=title))