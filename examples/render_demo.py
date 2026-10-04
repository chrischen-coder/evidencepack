"""Render the release figure directly from published measurements and captured repairs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ("prefix", "head_tail", "bm25", "evidencepack")
LABELS = ("Prefix", "Head / tail", "BM25", "EvidencePack")
BG, CARD, INK, MUTED = "#0d1422", "#152236", "#edf4ff", "#a0b0c8"
COLORS = ("#52637b", "#71819a", "#699ff2", "#45d3b0")


def box(fig, bounds, title, body, *, accent=COLORS[-1]):
    """Draw one explanatory card with explicit figure-relative geometry."""
    x, y, width, height = bounds
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.008,rounding_size=0.012",
        transform=fig.transFigure,
        facecolor=CARD,
        edgecolor="#28405d",
        linewidth=1,
    )
    fig.add_artist(patch)
    fig.text(x + 0.014, y + height - 0.040, title, color=accent, fontsize=13, weight="bold")
    fig.text(x + 0.014, y + height - 0.072, body, color=INK, fontsize=11, va="top", linespacing=1.6)


def chart(fig, bounds, title, subtitle, counts, *, denominator=12):
    """Plot measured counts with the denominator visible, including zero-result arms."""
    ax = fig.add_axes(bounds, facecolor=CARD)
    bars = ax.barh(range(4), counts, color=COLORS, height=0.53)
    ax.invert_yaxis()
    ax.set_xlim(0, denominator + 1.9)
    ax.set_ylim(3.7, -0.65)
    ax.set_yticks(range(4), LABELS, color=INK, fontsize=12)
    ax.set_xticks([0, 4, 8, 12], ["0", "4", "8", "12"], color=MUTED, fontsize=10)
    ax.tick_params(length=0, pad=9)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color="#28405d", linewidth=0.6)
    ax.set_title(title, loc="left", color=INK, fontsize=15, weight="bold", pad=40)
    ax.text(0, 1.065, subtitle, transform=ax.transAxes, color=MUTED, fontsize=11)
    for bar, value in zip(bars, counts, strict=True):
        ax.text(
            value + 0.22,
            bar.get_y() + bar.get_height() / 2,
            f"{value}/{denominator}",
            color=INK,
            va="center",
            fontsize=12,
            weight="bold",
        )


def main() -> None:
    """Combine evidence flow, an actual repair and equal-budget policy comparisons."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=ROOT / "docs/results/2026-10-04")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets/demo.png")
    args = parser.parse_args()
    cpu = json.loads((args.results / "linux/report.json").read_text())
    gpu = json.loads((args.results / "qwen4b-validation/report.json").read_text())
    rows = [
        json.loads(line) for line in (args.results / "linux/rows.jsonl").read_text().splitlines()
    ]
    row = next(
        r for r in rows if r["case"] == "real-port_mismatch-0" and r["policy"] == "evidencepack"
    )
    config_text = next(
        u["text"].splitlines()[0]
        for u in row["pack"]["excerpts"]
        if u["source"] == "configuration" and u["text"].startswith("CONFIG ")
    )
    config = json.loads(config_text.removeprefix("CONFIG "))
    repaired_port = row["repair"]["patch"]["upstream_port"]
    summary = cpu["real_faults"]["evidencepack"]
    reduction = 100 * (1 - summary["mean_used"] / summary["mean_raw_cost"])
    fig = plt.figure(figsize=(16, 10), facecolor=BG)
    fig.text(0.045, 0.942, "EvidencePack", color=INK, fontsize=34, weight="bold")
    fig.text(
        0.046,
        0.904,
        "Complete tool evidence. Bounded input. Checkable quotations.",
        color=MUTED,
        fontsize=15,
    )
    fig.text(
        0.955,
        0.945,
        "MEASURED LAB DEMO\n2026-10-04 · v0.1.0",
        color=COLORS[-1],
        fontsize=11,
        ha="right",
        va="top",
        linespacing=1.6,
    )
    steps = (
        ("1  Archive", "Exact tool output\nSHA-256 + invocation ID"),
        ("2  Pack", "Complete lines / JSON\nBudget includes metadata"),
        ("3  Diagnose", "Host delivers this pack\nModel returns cited quotes"),
        ("4  Verify", "Receipt binds exact quotes\nLive references pin originals"),
    )
    for index, (title, body) in enumerate(steps):
        x = 0.045 + index * 0.234
        box(fig, (x, 0.742, 0.213, 0.117), title, body)
        if index < 3:
            fig.text(x + 0.22, 0.796, "›", color=MUTED, fontsize=25, ha="center")
    box(
        fig,
        (0.045, 0.485, 0.44, 0.207),
        "Actual loopback repair · port fault",
        (
            f"CONFIG upstream_port={config['upstream_port']}\n"
            f"Backend LISTENER bound_port={repaired_port}\n"
            f"Minimal patch: upstream_port → {repaired_port}\n"
            f"Measured HTTP health: {row['repair']['before']} → {row['repair']['after']}"
        ),
    )
    box(
        fig,
        (0.515, 0.485, 0.44, 0.207),
        "Compact evidence without rewriting observations",
        (
            f"{summary['mean_raw_cost']:,.0f} raw bytes → "
            f"{summary['mean_used']:,.0f} packed bytes (means)\n"
            f"{reduction:.2f}% smaller · allowance {cpu['budget']:,} UTF-8 bytes\n"
            f"{summary['positive_quote_checks']} exact checks + "
            f"{summary['fabricated_quote_checks']} forged checks passed\n"
            f"Selection + receipt median {summary['median_ms']:.3f} ms on Linux"
        ),
    )
    chart(
        fig,
        (0.15, 0.15, 0.32, 0.225),
        "Complete failure / config / runtime chain",
        "12 live faults · 2,000-byte serialized evidence budget",
        [cpu["real_faults"][p]["complete"] for p in POLICIES],
    )
    chart(
        fig,
        (0.64, 0.15, 0.31, 0.225),
        "Correct patch + supported valid quotes",
        "Fresh 12 instances · Qwen3-4B · 1,000 native tokens",
        [gpu["policies"][p]["grounded_successes"] for p in POLICIES],
    )
    fig.text(
        0.045,
        0.071,
        "Both BM25 and EvidencePack: 12/12 rule repairs; 12/12 model patches on fresh instances.\n"
        "One submitted quote fails verification in each arm. "
        "Initial and final runs are published.",
        color=MUTED,
        fontsize=11,
        linespacing=1.5,
    )
    fig.text(
        0.045,
        0.023,
        "Controlled generated / loopback lab with an explicit comparison rule. "
        "No production or complete-agent superiority claim.  "
        "github.com/chrischen-coder/evidencepack",
        color=MUTED,
        fontsize=9,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160, facecolor=BG)
    plt.close(fig)
    print(args.output)


if __name__ == "__main__":
    main()
