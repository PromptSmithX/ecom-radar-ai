"""Command Line Interface for Trend Research Tool using Typer."""

from __future__ import annotations
import logging
import sys
from pathlib import Path
from typing import Optional

# Đảm bảo thư mục gốc dự án luôn nằm trong sys.path và console hỗ trợ UTF-8
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
from rich.console import Console
from rich.table import Table
from src.collectors.registry import collect_for_niche
from src.core.cache import cache
from src.core.config import load_niches, settings
from src.pipeline.runner import PipelineRunner

app = typer.Typer(help="AI Product Trend Research Tool CLI")
console = Console()


@app.command("list-niches")
def list_niches():
    """Lists all configured categories and niches."""
    category, niches = load_niches()
    console.print(f"\n[bold green]Danh mục:[/bold green] {category}")
    table = Table(title="Danh sách Niches & Seed Keywords", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Niche", style="bold")
    table.add_column("Seed Keywords", style="cyan")

    for idx, n in enumerate(niches, 1):
        table.add_row(str(idx), n.name, ", ".join(n.seed_keywords))

    console.print(table)


@app.command("collect")
def collect(
    niches_filter: Optional[str] = typer.Option("all", "--niches", "-n", help="Niche name, ID, or 'all'"),
):
    """Collects raw data for niches and saves to data/raw cache."""
    category, niches = load_niches()
    if niches_filter.lower() != "all":
        niches = [n for n in niches if niches_filter.lower() in n.name.lower() or niches_filter.lower() in (n.id or "").lower()]
        if not niches:
            console.print(f"[bold red]Lỗi:[/bold red] Không tìm thấy niche phù hợp với '{niches_filter}'.")
            raise typer.Exit(1)

    console.print(f"[bold blue]Bắt đầu thu thập dữ liệu cho {len(niches)} niche...[/bold blue]\n")
    for idx, niche in enumerate(niches, 1):
        console.print(f"[{idx}/{len(niches)}] Thu thập: [bold yellow]{niche.name}[/bold yellow]...")
        items = collect_for_niche(niche)
        console.print(f"   -> Thu thập được [green]{len(items)}[/green] bằng chứng từ {len({e.source for e in items})} nguồn.")

    console.print("\n[bold green]✓ Thu thập hoàn tất![/bold green] Dữ liệu thô đã được lưu vào [cyan]data/raw/[/cyan].")


@app.command("run")
def run(
    niches_filter: Optional[str] = typer.Option("all", "--niches", "-n", help="Tên niche hoặc 'all'"),
    writer_provider: Optional[str] = typer.Option(None, "--writer", "-w", help="LLM Provider cho bước viết: gemini | openai | mock"),
    writer_model: Optional[str] = typer.Option(None, "--writer-model", help="Tên model viết báo cáo"),
    digest_provider: Optional[str] = typer.Option(None, "--digest", "-d", help="LLM Provider cho bước digest: gemini | openai | mock"),
    digest_model: Optional[str] = typer.Option(None, "--digest-model", help="Tên model digest"),
    use_cache: bool = typer.Option(True, "--cache/--no-cache", help="Có sử dụng dữ liệu đã cache hay không"),
):
    """Executes the full AI trend research pipeline and outputs a Markdown report."""
    category, all_niches = load_niches()
    if niches_filter.lower() == "all":
        selected_niches = all_niches
    else:
        selected_niches = [n for n in all_niches if niches_filter.lower() in n.name.lower() or niches_filter.lower() in (n.id or "").lower()]
        if not selected_niches:
            console.print(f"[bold red]Lỗi:[/bold red] Không tìm thấy niche phù hợp với '{niches_filter}'.")
            raise typer.Exit(1)

    # Determine default provider
    w_provider = writer_provider or settings.llm.writer.provider

    # Check API key availability — warn loudly, do NOT silently fall back to mock
    missing_key = False
    if w_provider == "gemini" and not settings.gemini_api_key:
        console.print("[bold red]❌ Lỗi: GEMINI_API_KEY chưa được cấu hình trong .env[/bold red]")
        console.print("[yellow]   Hãy chạy lại sau khi đặt key, hoặc dùng '--writer mock' nếu chỉ muốn thử nghiệm.[/yellow]")
        missing_key = True
    elif w_provider == "openai" and not settings.openai_api_key:
        console.print("[bold red]❌ Lỗi: OPENAI_API_KEY chưa được cấu hình trong .env[/bold red]")
        console.print("[yellow]   Hãy chạy lại sau khi đặt key, hoặc dùng '--writer mock' nếu chỉ muốn thử nghiệm.[/yellow]")
        missing_key = True

    if missing_key:
        raise typer.Exit(1)

    d_provider = digest_provider or (w_provider if w_provider == "mock" else settings.llm.digest.provider)
    if d_provider == "gemini" and not settings.gemini_api_key:
        console.print("[bold red]❌ Lỗi: GEMINI_API_KEY chưa cấu hình cho bước digest.[/bold red]")
        raise typer.Exit(1)
    elif d_provider == "openai" and not settings.openai_api_key:
        console.print("[bold red]❌ Lỗi: OPENAI_API_KEY chưa cấu hình cho bước digest.[/bold red]")
        raise typer.Exit(1)

    # When using mock, display a clear warning so the user knows output is not real data
    if w_provider == "mock":
        console.print("[bold yellow]⚠️  Chế độ MOCK — báo cáo sẽ chứa dữ liệu mẫu, không dùng để ra quyết định kinh doanh.[/bold yellow]\n")

    runner = PipelineRunner(
        digest_provider=d_provider,
        digest_model=digest_model,
        writer_provider=w_provider,
        writer_model=writer_model,
        summary_provider=w_provider,
        summary_model=writer_model,
        use_cache=use_cache,
    )

    console.print(f"\n[bold green]=== BẮT ĐẦU NGHIÊN CỨU XU HƯỚNG ===[/bold green]")
    console.print(f"Danh mục: [bold cyan]{category}[/bold cyan]")
    console.print(f"Số lượng Niche: [bold cyan]{len(selected_niches)}[/bold cyan]")
    console.print(f"Writer LLM: [bold]{w_provider}[/bold] | Digest LLM: [bold]{d_provider}[/bold] | Cache: [bold]{use_cache}[/bold]\n")

    def progress_callback(stage: str, fraction: float, msg: str):
        pct = int(fraction * 100)
        console.print(f"[{pct:3d}%] [[magenta]{stage}[/magenta]] {msg}")

    final_report, saved_path, _ = runner.run(
        selected_niches=selected_niches,
        category=category,
        progress_cb=progress_callback,
    )

    console.print("\n" + "=" * 60)
    console.print(f"[bold green]✓ BÁO CÁO ĐÃ XUẤT THÀNH CÔNG![/bold green]")
    console.print(f"📁 Đường dẫn: [bold cyan]{saved_path}[/bold cyan]")
    console.print(f"💰 Ước tính chi phí: [bold yellow]${final_report.cost_usd:.4f}[/bold yellow] ({final_report.total_input_tokens} in / {final_report.total_output_tokens} out tokens)")

    # Print rankings table
    rank_table = Table(title="Xếp hạng Niche Tiềm Năng", show_header=True)
    rank_table.add_column("Hạng", justify="center")
    rank_table.add_column("Niche")
    rank_table.add_column("Điểm", justify="center")
    rank_table.add_column("Lý do")

    for r in final_report.ranking:
        rank_table.add_row(str(r.rank), r.niche, f"{r.score}/10", r.reason)

    console.print(rank_table)


@app.command("clear-cache")
def clear_cache():
    """Clears all cached raw data and evidence files."""
    cache.clear()
    console.print("[bold green]✓ Đã xóa toàn bộ cache tại data/raw và data/evidence.[/bold green]")


if __name__ == "__main__":
    app()
