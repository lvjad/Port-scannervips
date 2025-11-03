import ipaddress
import os
import platform
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    from rich.progress import Progress, BarColumn, TextColumn, MofNCompleteColumn, TimeRemainingColumn
    from rich.text import Text
    from rich.panel import Panel
    from rich.align import Align
except ImportError:
    print("❗  Missing dependencies. Install with:  pip install rich")
    sys.exit(1)


console = Console()

MAX_THREADS = 200
PING_TIMEOUT_MS = 800
OS = platform.system().lower()

BANNER = r"""
▄▄▄█████▓ ██░ ██ ▓█████  ███▄    █ ▓█████▄  ▒█████  
▓  ██▒ ▓▒▓██░ ██▒▓█   ▀  ██ ▀█   █ ▒██▀ ██▌▒██▒  ██▒
▒ ▓██░ ▒░▒██▀▀██░▒███   ▓██  ▀█ ██▒░██   █▌▒██░  ██▒
░ ▓██▓ ░ ░▓█ ░██ ▒▓█  ▄ ▓██▒  ▐▌██▒░▓█▄   ▌▒██   ██░
  ▒██▒ ░ ░▓█▒░██▓░▒████▒▒██░   ▓██░░▒████▓ ░ ████▓▒░
  ▒ ░░    ▒ ░░▒░▒░░ ▒░ ░░ ▒░   ▒ ▒  ▒▒▓  ▒ ░ ▒░▒░▒░ 
    ░     ▒ ░▒░ ░ ░ ░  ░░ ░░   ░ ▒░ ░ ▒  ▒   ░ ▒ ▒░ 
  ░       ░  ░░ ░   ░      ░   ░ ░  ░ ░  ░ ░ ░ ░ ▒  
          ░  ░  ░   ░  ░         ░    ░        ░ ░  
                                    ░              
"""

def build_ping_cmd(host: str) -> list[str]:
    """Return OS-specific ping command list."""
    if OS == "windows":
        return ["ping", "-n", "1", "-w", str(PING_TIMEOUT_MS), host]
    return ["ping", "-c", "1", "-W", str(PING_TIMEOUT_MS // 1000), host]


def ping(host: str) -> tuple[str, bool]:
    """Return (host, is_alive)."""
    try:
        with open(os.devnull, "wb") as DEVNULL:
            result = subprocess.run(
                build_ping_cmd(host),
                stdout=DEVNULL,
                stderr=DEVNULL,
            )
        alive = result.returncode == 0
    except Exception:
        alive = False
    return host, alive


def sweep_network(subnet: str) -> list[tuple[str, bool]]:
    """Return list of (ip, alive) tuples."""
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError as e:
        console.print(f"[red]Invalid subnet: {e}[/red]")
        sys.exit(1)

    hosts = [str(ip) for ip in network.hosts()]
    results: list[tuple[str, bool]] = []

    progress = Progress(
        TextColumn("[bold blue]{task.description}", justify="right"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
    )
    task = progress.add_task("Sweeping", total=len(hosts))

    table = Table(title=f"Live Results  •  {subnet}")
    table.add_column("IP Address", style="cyan")
    table.add_column("Status", justify="center")

    def update_table():
        table.rows.clear()
        for ip, alive in sorted(results, key=lambda x: ipaddress.IPv4Address(x[0])):
            status = Text("UP", style="bold green") if alive else Text("DOWN", style="red")
            table.add_row(ip, status)

    with Live(Panel(Align.center(table), border_style="bright_blue"), refresh_per_second=4, console=console):
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            future_to_host = {executor.submit(ping, h): h for h in hosts}
            for future in as_completed(future_to_host):
                results.append(future.result())
                progress.advance(task)
                update_table()
    return results


def main() -> None:
    console.clear()
    console.print(Panel(Align.center(BANNER, vertical="middle"), border_style="bright_blue"))

    try:
        subnet = console.input("\n[bold cyan]Enter subnet to sweep (e.g. 192.168.1.0/24): [/bold cyan]").strip()
        if not subnet:
            console.print("\n[yellow]No subnet entered. Exiting.[/yellow]")
            return
    except KeyboardInterrupt:
        console.print("\n[yellow]Aborted.[/yellow]")
        return

    console.print()
    start_time = datetime.now()
    results = sweep_network(subnet)
    end_time = datetime.now()

    up_hosts = [ip for ip, alive in results if alive]

    console.print()
    console.print(Panel(
        f"[bold green]Sweep finished in {(end_time - start_time).total_seconds():.2f}s[/bold green]\n"
        f"Hosts UP: [green]{len(up_hosts)}[/green] / {len(results)}",
        title="Summary",
        border_style="bright_green"
    ))

    if up_hosts:
        console.print("\n[bold underline]Discovered devices:[/bold underline]")
        for ip in up_hosts:
            try:
                hostname = socket.gethostbyaddr(ip)[0]
            except socket.herror:
                hostname = "—"
            console.print(f"  • {ip}  [dim]({hostname})[/dim]")
    else:
        console.print("\n[dim]No live hosts found.[/dim]")


if __name__ == "__main__":

    main()

