"""Aegis CLI — main entry point."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Aegis — agentic data quality framework")
console = Console()

rules_app = typer.Typer(help="Manage built-in rule templates")
app.add_typer(rules_app, name="rules")


@app.command()
def init(
    output: Path = typer.Option(
        Path("rules.yaml"), "--output", "-o", help="Output file path"
    ),
) -> None:
    """Generate an example rules.yaml file."""
    example = """\
# Aegis rules example
rules:
  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: orders_no_nulls
      severity: critical
      domain: retail
    scope:
      warehouse: duckdb
      table: orders
      columns: [order_id]
    logic:
      type: not_null

  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: orders_positive_revenue
      severity: high
      domain: retail
    scope:
      warehouse: duckdb
      table: orders
    logic:
      type: sql_expression
      expression: "revenue >= 0"
    diagnosis:
      common_causes:
        - "Refund logic inverted"
        - "Currency conversion failure"
"""
    output.write_text(example)
    console.print(f"[green]Created {output}[/green]")


@app.command()
def run(
    config: Path = typer.Argument(..., help="Path to rules YAML file"),
    db: str = typer.Option(":memory:", "--db", help="DuckDB path (or :memory:)"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM diagnosis (offline mode)"),
    llm: str = typer.Option("anthropic", "--llm", help="LLM provider: anthropic|openai|ollama"),
    llm_model: str | None = typer.Option(None, "--llm-model", help="Override default model name"),
    ollama_host: str = typer.Option(
        "http://localhost:11434", "--ollama-host", help="Base URL for local Ollama instance"
    ),
    output_json: Path | None = typer.Option(
        None, "--output-json", "-o", help="Write JSON report to file"
    ),
    notify: str | None = typer.Option(
        None, "--notify", help="Slack webhook URL (or set AEGIS_SLACK_WEBHOOK)"
    ),
    notify_on: str = typer.Option(
        "failures", "--notify-on", help="When to notify: all|failures|critical"
    ),
) -> None:
    """Run data quality checks defined in a YAML config file."""
    asyncio.run(_run(config, db, no_llm, llm, llm_model, ollama_host, output_json, notify, notify_on))


def _build_llm_adapter(provider: str, model: str | None, ollama_host: str = "http://localhost:11434"):
    """Resolve provider name to an LLMAdapter instance."""
    if provider == "anthropic":
        from ..adapters.llm.anthropic import AnthropicAdapter
        return AnthropicAdapter(**({"model": model} if model else {}))
    if provider == "openai":
        try:
            from ..adapters.llm.openai import OpenAIAdapter
        except ImportError:
            console.print("[red]openai package not installed. Run: pip install aegis-dq[openai][/red]")
            raise typer.Exit(1)
        return OpenAIAdapter(**({"model": model} if model else {}))
    if provider == "ollama":
        from ..adapters.llm.ollama import OllamaAdapter
        kwargs: dict = {"base_url": ollama_host}
        if model:
            kwargs["model"] = model
        return OllamaAdapter(**kwargs)
    console.print(f"[red]Unknown LLM provider '{provider}'. Choose: anthropic|openai|ollama[/red]")
    raise typer.Exit(1)


async def _run(
    config: Path,
    db: str,
    no_llm: bool,
    llm_provider: str,
    llm_model: str | None,
    ollama_host: str,
    output_json: Path | None,
    notify: str | None,
    notify_on: str,
) -> None:
    from ..adapters.warehouse.duckdb import DuckDBAdapter
    from ..core.agent import AegisAgent
    from ..memory.store import save_run
    from ..rules.parser import load_rules

    console.print(f"[bold blue]Aegis DQ[/bold blue] — loading rules from {config}")

    try:
        rules = load_rules(config)
    except Exception as e:
        console.print(f"[red]Failed to load rules: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"Loaded [bold]{len(rules)}[/bold] rules")

    warehouse = DuckDBAdapter(db)
    llm = None if no_llm else _build_llm_adapter(llm_provider, llm_model, ollama_host)

    if llm:
        provider_label = type(llm).__name__.replace("Adapter", "")
        model_label = getattr(llm, "_model", "")
        console.print(f"LLM: [bold]{provider_label}[/bold] ({model_label})")

    agent = AegisAgent(warehouse_adapter=warehouse, llm_adapter=llm)

    with console.status("Running validation..."):
        final_state = await agent.run(rules, triggered_by="cli")

    report = final_state["report"]

    # Print summary table
    s = report.get("summary", {})
    table = Table(title="Aegis Validation Report")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Rules checked", str(s.get("total_rules", 0)))
    table.add_row("Passed", f"[green]{s.get('passed', 0)}[/green]")
    table.add_row("Failed", f"[red]{s.get('failed', 0)}[/red]")
    table.add_row("Pass rate", f"{s.get('pass_rate', 0)}%")
    table.add_row("LLM cost", f"${report.get('cost_usd', 0):.6f}")
    console.print(table)

    # Print failures
    if report.get("failures"):
        console.print("\n[bold red]Failures:[/bold red]")
        for f in report["failures"]:
            console.print(
                f"\n  [bold]{f['rule_id']}[/bold] ([red]{f['severity']}[/red]) — {f['table']}"
            )
            console.print(f"  Rows failed: {f['rows_failed']} / {f['rows_checked']}")
            if "diagnosis" in f:
                d = f["diagnosis"]
                console.print(f"  [yellow]Explanation:[/yellow] {d.get('explanation', '')}")
                console.print(f"  [yellow]Likely cause:[/yellow] {d.get('likely_cause', '')}")
                console.print(f"  [yellow]Action:[/yellow] {d.get('suggested_action', '')}")

    # Save to history
    await save_run(report)

    # Write JSON if requested
    if output_json:
        output_json.write_text(json.dumps(report, indent=2))
        console.print(f"\n[green]Report written to {output_json}[/green]")

    # Slack notification
    if notify or os.environ.get("AEGIS_SLACK_WEBHOOK"):
        from ..adapters.output.slack import NotifyOn, post_to_slack
        try:
            notify_on_enum = NotifyOn(notify_on)
        except ValueError:
            console.print(f"[red]Invalid --notify-on value '{notify_on}'. Choose: all|failures|critical[/red]")
            raise typer.Exit(1)
        sent = await post_to_slack(report, webhook_url=notify, notify_on=notify_on_enum)
        if sent:
            console.print("[green]Slack notification sent[/green]")

    # Exit with non-zero if failures
    if s.get("failed", 0) > 0:
        raise typer.Exit(1)


@app.command()
def validate(
    config: Path = typer.Argument(..., help="Path to rules YAML file"),
    warnings: bool = typer.Option(True, "--warnings/--no-warnings", help="Show warnings"),
) -> None:
    """Check rule YAML syntax and schema correctness without hitting any warehouse."""
    from ..rules.validator import validate_file

    report = validate_file(config)

    console.print(f"\n[bold blue]Aegis validate[/bold blue] — {config}\n")

    for r in report.results:
        label = r.rule_id or f"rule[{r.index}]"
        if r.valid:
            warn_str = f"  [yellow]{len(r.warnings)} warning(s)[/yellow]" if r.warnings else ""
            console.print(f"  [green]✓[/green] {label}{warn_str}")
            if warnings:
                for w in r.warnings:
                    console.print(f"      [yellow]⚠[/yellow]  {w}")
        else:
            console.print(f"  [red]✗[/red] {label}")
            for e in r.errors:
                console.print(f"      [red]✗[/red]  {e}")
            if warnings:
                for w in r.warnings:
                    console.print(f"      [yellow]⚠[/yellow]  {w}")

    console.print()
    if report.ok:
        console.print(
            f"[bold green]All {report.total} rule(s) valid.[/bold green]"
        )
    else:
        console.print(
            f"[bold red]{report.invalid_count} of {report.total} rule(s) invalid.[/bold red]"
        )
        raise typer.Exit(1)


audit_app = typer.Typer(help="Inspect audit trails and trajectories")
app.add_typer(audit_app, name="audit")

dbt_app = typer.Typer(help="dbt integration")
app.add_typer(dbt_app, name="dbt")


@dbt_app.command("generate")
def dbt_generate(
    manifest: Path = typer.Argument(..., help="Path to dbt manifest.json"),
    output: Path = typer.Option(Path("rules.yaml"), "--output", "-o"),
    warehouse: str = typer.Option("duckdb", "--warehouse", "-w", help="Warehouse type for generated rules"),
) -> None:
    """Generate Aegis rules YAML from a dbt manifest.json."""
    from ..integrations.dbt.parser import load_manifest, manifest_to_yaml

    if not manifest.exists():
        console.print(f"[red]Manifest not found: {manifest}[/red]")
        raise typer.Exit(1)

    try:
        mf = load_manifest(manifest)
    except Exception as e:
        console.print(f"[red]Failed to parse manifest: {e}[/red]")
        raise typer.Exit(1)

    yaml_str = manifest_to_yaml(mf)

    # Patch warehouse if user specified something other than the default
    if warehouse != "duckdb":
        yaml_str = yaml_str.replace("warehouse: duckdb", f"warehouse: {warehouse}")

    output.write_text(yaml_str)
    console.print(f"[green]Rules written to {output}[/green]")


@audit_app.command("trajectory")
def audit_trajectory(
    run_id: str = typer.Argument(..., help="Run ID to inspect"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format: table|json|sharegpt"),
) -> None:
    """Show the decision trajectory for a completed run."""
    asyncio.run(_audit_trajectory(run_id, fmt))


async def _audit_trajectory(run_id: str, fmt: str) -> None:
    from ..audit.logger import get_decisions
    from ..audit.trajectory import export_sharegpt

    if fmt == "sharegpt":
        data = await export_sharegpt(run_id)
        console.print_json(json.dumps(data, indent=2))
        return

    decisions = await get_decisions(run_id)
    if not decisions:
        console.print(f"[yellow]No decisions found for run {run_id}[/yellow]")
        raise typer.Exit(1)

    if fmt == "json":
        console.print_json(json.dumps(decisions, indent=2))
        return

    table = Table(title=f"Trajectory — {run_id}")
    table.add_column("#", style="dim", width=4)
    table.add_column("Step", style="cyan", no_wrap=True)
    table.add_column("Model", style="magenta")
    table.add_column("In tok", justify="right")
    table.add_column("Out tok", justify="right")
    table.add_column("Cost $", justify="right")
    table.add_column("ms", justify="right")
    table.add_column("Output summary", style="white")

    for i, d in enumerate(decisions, 1):
        table.add_row(
            str(i),
            d["step"],
            d.get("model") or "—",
            str(d.get("input_tokens") or 0),
            str(d.get("output_tokens") or 0),
            f"{d.get('cost_usd', 0):.6f}",
            f"{d.get('duration_ms', 0):.0f}",
            (d.get("output_summary") or "")[:60],
        )

    console.print(table)
    console.print(f"[bold]{len(decisions)}[/bold] decision(s)")


@audit_app.command("list-runs")
def audit_list_runs() -> None:
    """List all run IDs in the audit database, newest first."""
    asyncio.run(_audit_list_runs())


async def _audit_list_runs() -> None:
    from ..audit.trajectory import list_run_ids

    run_ids = await list_run_ids()
    if not run_ids:
        console.print("[yellow]No runs found in audit database[/yellow]")
        return
    for rid in run_ids:
        console.print(rid)


@audit_app.command("export-dataset")
def audit_export_dataset(
    output: Path = typer.Argument(..., help="Output file path (.jsonl or .json)"),
    run_ids: list[str] = typer.Option([], "--run-id", "-r", help="Run IDs to include (repeatable); omit for all"),
    fmt: str = typer.Option("jsonl", "--format", "-f", help="Output format: jsonl|json"),
    min_turns: int = typer.Option(1, "--min-turns", help="Min LLM turns per run (quality filter)"),
    no_filter: bool = typer.Option(False, "--no-filter", help="Disable quality filtering"),
) -> None:
    """Export run trajectories as a ShareGPT fine-tuning dataset."""
    asyncio.run(_audit_export_dataset(output, run_ids, fmt, min_turns, not no_filter))


async def _audit_export_dataset(
    output: Path, run_ids: list[str], fmt: str, min_turns: int, filter_quality: bool
) -> None:
    from ..audit.trajectory import export_dataset, list_run_ids

    ids = run_ids or await list_run_ids()
    if not ids:
        console.print("[yellow]No runs found[/yellow]")
        raise typer.Exit(1)

    console.print(f"Exporting [bold]{len(ids)}[/bold] run(s) → [cyan]{output}[/cyan]")
    stats = await export_dataset(
        ids, output, fmt=fmt, min_llm_turns=min_turns, filter_quality=filter_quality
    )

    console.print(
        f"[green]✓[/green] Exported [bold]{stats['exported']}[/bold] samples "
        f"({stats['skipped']} skipped by quality filter) — "
        f"{stats['total_turns']} turns, {stats['total_tokens']} tokens"
    )


@audit_app.command("search")
def audit_search(
    query: str = typer.Argument(..., help="Full-text search query"),
    run_id: str | None = typer.Option(None, "--run-id", "-r", help="Filter to specific run"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """Full-text search over audit decision trails."""
    asyncio.run(_audit_search(query, run_id, limit))


async def _audit_search(query: str, run_id: str | None, limit: int) -> None:
    from ..audit.search import search_decisions

    results = await search_decisions(query, run_id=run_id, limit=limit)
    if not results:
        console.print("[yellow]No results found[/yellow]")
        return
    table = Table(title=f"Search: {query!r}")
    table.add_column("Run ID", style="cyan")
    table.add_column("Step", style="magenta")
    table.add_column("Output", style="white")
    for r in results:
        table.add_row(r["run_id"], r["step"], (r.get("output_summary") or "")[:80])
    console.print(table)
    console.print(f"[bold]{len(results)}[/bold] result(s)")


@app.command()
def mcp(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(8765, "--port", "-p", help="Port to listen on"),
    transport: str = typer.Option("stdio", "--transport", help="Transport: stdio|sse"),
) -> None:
    """Start the Aegis MCP server for tool use by Claude and other LLMs."""
    from .mcp_runner import run_mcp_server
    run_mcp_server(host=host, port=port, transport=transport)


@rules_app.command("list")
def rules_list(
    category: str | None = typer.Option(None, "--category", "-c", help="Filter by category"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all 30 built-in rule templates."""
    from ..rules.builtin.catalog import CATALOG

    templates = CATALOG
    if category:
        templates = [t for t in templates if t.category == category]

    if json_output:
        import dataclasses

        data = [dataclasses.asdict(t) for t in templates]
        console.print_json(json.dumps(data))
        return

    table = Table(title="Aegis Built-in Rule Templates")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Category", style="magenta")
    table.add_column("Description", style="white")
    table.add_column("Severity", style="yellow")

    for t in templates:
        table.add_row(t.name, t.category, t.description, t.default_severity)

    console.print(table)
    console.print(f"\n[bold]{len(templates)}[/bold] template(s) shown")


if __name__ == "__main__":
    app()
