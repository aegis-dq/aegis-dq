"""Aegis CLI — main entry point."""

from __future__ import annotations

import asyncio
import json
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
    llm: str = typer.Option("anthropic", "--llm", help="LLM provider: anthropic|openai"),
    llm_model: str | None = typer.Option(None, "--llm-model", help="Override default model name"),
    output_json: Path | None = typer.Option(
        None, "--output-json", "-o", help="Write JSON report to file"
    ),
) -> None:
    """Run data quality checks defined in a YAML config file."""
    asyncio.run(_run(config, db, no_llm, llm, llm_model, output_json))


def _build_llm_adapter(provider: str, model: str | None):
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
    console.print(f"[red]Unknown LLM provider '{provider}'. Choose: anthropic|openai[/red]")
    raise typer.Exit(1)


async def _run(
    config: Path,
    db: str,
    no_llm: bool,
    llm_provider: str,
    llm_model: str | None,
    output_json: Path | None,
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
    llm = None if no_llm else _build_llm_adapter(llm_provider, llm_model)

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

    # Exit with non-zero if failures
    if s.get("failed", 0) > 0:
        raise typer.Exit(1)


audit_app = typer.Typer(help="Inspect audit trails and trajectories")
app.add_typer(audit_app, name="audit")


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
