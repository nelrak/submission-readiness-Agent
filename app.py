"""
Submission Readiness Scorecard Agent
=====================================
Accepts: PDF, DOCX, TXT, or plain text input
Checks against: ICH M4, ICH Q1A, FDA 21 CFR, EMA guidelines
Outputs: Pass/Fail checks + % score per module + prioritised fix list

Requirements:
    pip install anthropic python-docx pymupdf rich
"""

import os
import json
import argparse
import sys
from pathlib import Path

# ── Optional rich for pretty terminal output ──────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import print as rprint
    RICH = True
    console = Console()
except ImportError:
    RICH = False
    console = None

import anthropic


# ══════════════════════════════════════════════════════════════════════════════
# 1.  FILE READERS
# ══════════════════════════════════════════════════════════════════════════════

def read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_pdf(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n".join(pages)
    except ImportError:
        print("pymupdf not installed. Run: pip install pymupdf")
        sys.exit(1)


def read_docx(path: Path) -> str:
    try:
        from docx import Document
        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except ImportError:
        print("python-docx not installed. Run: pip install python-docx")
        sys.exit(1)


def load_submission_file(file_path: str) -> str:
    """
    Load a submission plan / dossier from a file.
    Supported formats: .pdf  .docx  .doc  .txt  .md
    """
    path = Path(file_path)
    if not path.exists():
        print(f"[ERROR] File not found: {file_path}")
        sys.exit(1)

    suffix = path.suffix.lower()
    print(f"  Loading {path.name} ({suffix}) …")

    if suffix == ".pdf":
        content = read_pdf(path)
    elif suffix in (".docx", ".doc"):
        content = read_docx(path)
    elif suffix in (".txt", ".md"):
        content = read_txt(path)
    else:
        print(f"[ERROR] Unsupported file type '{suffix}'. Use PDF, DOCX, TXT or MD.")
        sys.exit(1)

    word_count = len(content.split())
    print(f"  Extracted {word_count:,} words from {path.name}")

    # Truncate very large documents to ~6000 words to stay within token budget
    words = content.split()
    if len(words) > 6000:
        content = " ".join(words[:6000])
        print(f"  Truncated to first 6,000 words for API call.")

    return content


# ══════════════════════════════════════════════════════════════════════════════
# 2.  PROMPT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a senior regulatory affairs expert (20+ years) with deep expertise in 
NDA/MAA submissions, ICH guidelines, FDA 21 CFR, and EMA requirements. 
You evaluate submission dossiers for readiness and provide precise, actionable feedback 
referencing real guidelines."""

def build_prompt(content: str, region: str, product_type: str) -> str:
    region_label = {
        "fda":  "FDA (US NDA)",
        "ema":  "EMA (EU MAA)",
        "both": "FDA (US NDA) and EMA (EU MAA)"
    }.get(region, "FDA and EMA")

    product_label = {
        "small_molecule": "Small molecule drug product",
        "biologic":       "Biologic / biosimilar",
        "atmp":           "Advanced therapy medicinal product (ATMP / gene therapy)"
    }.get(product_type, "Small molecule drug product")

    return f"""You are reviewing a submission plan / dossier extract for regulatory readiness.

Target region: {region_label}
Product type:  {product_label}

Dossier content:
---
{content}
---

Evaluate this submission against:
- ICH M4 CTD structure (Modules 1–5)
- ICH Q1A(R2) stability requirements
- ICH Q8/Q9/Q10/Q11 CMC guidelines  
- Regional requirements: {region_label}
- Paediatric requirements (PIP / iPSP)
- Risk management requirements (RMP / REMS where applicable)

Respond ONLY with a valid JSON object — no markdown fences, no preamble, no trailing text.

JSON schema (fill every field):
{{
  "score": <integer 0–100>,
  "passed": <integer — number of passed checks>,
  "critical_count": <integer>,
  "warning_count": <integer>,
  "readiness_label": "<Not ready | Needs work | Nearly ready | Ready to file>",
  "modules": [
    {{"name": "Module 1 – Administrative",   "score": <0–100>, "status": "<green|amber|red>"}},
    {{"name": "Module 2 – Summaries",        "score": <0–100>, "status": "<green|amber|red>"}},
    {{"name": "Module 3 – CMC",              "score": <0–100>, "status": "<green|amber|red>"}},
    {{"name": "Module 4 – Non-clinical",     "score": <0–100>, "status": "<green|amber|red>"}},
    {{"name": "Module 5 – Clinical",         "score": <0–100>, "status": "<green|amber|red>"}}
  ],
  "critical": [
    {{
      "title": "<short issue title>",
      "comment": "<specific regulatory comment referencing ICH/FDA/EMA guideline>",
      "guideline": "<e.g. ICH Q1A(R2), FDA 21 CFR 314.50>"
    }}
  ],
  "warnings": [
    {{
      "title": "<short issue title>",
      "comment": "<specific comment>",
      "guideline": "<guideline reference>"
    }}
  ],
  "passed_checks": [
    {{
      "title": "<what passed>",
      "comment": "<brief confirmation note>"
    }}
  ],
  "fix_list": [
    {{
      "priority": "<P1|P2|P3>",
      "action": "<specific action — what to do, not just what is missing>",
      "effort": "<Low|Medium|High>",
      "owner": "<e.g. CMC team | Clinical team | Regulatory affairs>"
    }}
  ],
  "summary": "<2–3 sentence overall assessment of the dossier>"
}}

Rules:
- P1 = filing blocker (critical gap), P2 = strongly recommended, P3 = nice-to-have
- Return 3–8 critical issues, 2–6 warnings, 3–10 passed checks, 4–10 fix list items
- Be specific — reference actual guideline sections and CTD locations
- If content is sparse, still evaluate based on what is NOT mentioned
"""


# ══════════════════════════════════════════════════════════════════════════════
# 3.  API CALL
# ══════════════════════════════════════════════════════════════════════════════

def run_scorecard(content: str, region: str, product_type: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    print("  Calling Anthropic API …")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": build_prompt(content, region, product_type)}
        ]
    )

    raw = response.content[0].text.strip()
    # Strip accidental markdown fences
    raw = raw.replace("```json", "").replace("```", "").strip()

    result = json.loads(raw)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 4.  OUTPUT RENDERER
# ══════════════════════════════════════════════════════════════════════════════

STATUS_ICON = {"green": "✓", "amber": "⚠", "red": "✗"}
PRIORITY_LABEL = {"P1": "CRITICAL", "P2": "WARNING ", "P3": "INFO    "}


def render_plain(result: dict, output_file: str | None = None):
    lines = []
    lines.append("=" * 70)
    lines.append("  SUBMISSION READINESS SCORECARD")
    lines.append("=" * 70)
    lines.append(f"  Overall score   : {result['score']}%")
    lines.append(f"  Readiness       : {result['readiness_label']}")
    lines.append(f"  Checks passed   : {result['passed']}")
    lines.append(f"  Critical gaps   : {result['critical_count']}")
    lines.append(f"  Warnings        : {result['warning_count']}")
    lines.append("")
    lines.append(f"  Summary: {result.get('summary', '')}")
    lines.append("")

    lines.append("── MODULE SCORES " + "─" * 54)
    for m in result["modules"]:
        icon = STATUS_ICON.get(m["status"], "?")
        bar_filled = int(m["score"] / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        lines.append(f"  {icon}  {m['name']:<35} {bar}  {m['score']}%")

    lines.append("")
    lines.append("── CRITICAL GAPS (filing blockers) " + "─" * 35)
    for i, c in enumerate(result["critical"], 1):
        lines.append(f"  {i}. {c['title']}")
        lines.append(f"     {c['comment']}")
        lines.append(f"     Guideline: {c.get('guideline', 'N/A')}")
        lines.append("")

    lines.append("── WARNINGS " + "─" * 58)
    for i, w in enumerate(result["warnings"], 1):
        lines.append(f"  {i}. {w['title']}")
        lines.append(f"     {w['comment']}")
        lines.append(f"     Guideline: {w.get('guideline', 'N/A')}")
        lines.append("")

    lines.append("── PASSED CHECKS " + "─" * 53)
    for p in result["passed_checks"]:
        lines.append(f"  ✓  {p['title']}")
        lines.append(f"     {p['comment']}")
    lines.append("")

    lines.append("── PRIORITISED FIX LIST " + "─" * 46)
    for i, f in enumerate(result["fix_list"], 1):
        label = PRIORITY_LABEL.get(f["priority"], f["priority"])
        effort = f.get("effort", "")
        owner  = f.get("owner", "")
        lines.append(f"  {i:>2}. [{label}] {f['action']}")
        lines.append(f"      Effort: {effort}   Owner: {owner}")
        lines.append("")

    lines.append("=" * 70)
    output = "\n".join(lines)
    print(output)

    if output_file:
        Path(output_file).write_text(output, encoding="utf-8")
        print(f"\n  Report saved to: {output_file}")


def render_rich(result: dict, output_file: str | None = None):
    score = result["score"]
    score_color = "green" if score >= 80 else "yellow" if score >= 60 else "red"

    console.print()
    console.print(Panel.fit(
        f"[bold]Overall score:[/bold] [{score_color}]{score}%[/{score_color}]   "
        f"[bold]Readiness:[/bold] {result['readiness_label']}   "
        f"[bold]Passed:[/bold] {result['passed']}   "
        f"[bold]Critical:[/bold] [red]{result['critical_count']}[/red]   "
        f"[bold]Warnings:[/bold] [yellow]{result['warning_count']}[/yellow]",
        title="[bold]Submission Readiness Scorecard[/bold]",
        border_style="blue"
    ))

    if result.get("summary"):
        console.print(f"\n[dim]{result['summary']}[/dim]\n")

    # Module scores table
    mod_table = Table(title="Module Scores", show_header=True, header_style="bold")
    mod_table.add_column("Module", style="white", width=38)
    mod_table.add_column("Score", justify="right", width=8)
    mod_table.add_column("Bar", width=22)
    mod_table.add_column("Status", width=8)
    for m in result["modules"]:
        s = m["score"]
        col = "green" if m["status"] == "green" else "yellow" if m["status"] == "amber" else "red"
        bar = f"[{col}]{'█' * int(s/5)}[/{col}]" + "░" * (20 - int(s/5))
        icon = {"green": "✓", "amber": "⚠", "red": "✗"}.get(m["status"], "?")
        mod_table.add_row(m["name"], f"[{col}]{s}%[/{col}]", bar, f"[{col}]{icon}[/{col}]")
    console.print(mod_table)

    # Critical gaps
    if result["critical"]:
        console.print("\n[bold red]Critical Gaps — filing blockers[/bold red]")
        for i, c in enumerate(result["critical"], 1):
            console.print(f"  [red]{i}.[/red] [bold]{c['title']}[/bold]")
            console.print(f"     {c['comment']}")
            console.print(f"     [dim]Guideline: {c.get('guideline', 'N/A')}[/dim]")

    # Warnings
    if result["warnings"]:
        console.print("\n[bold yellow]Warnings[/bold yellow]")
        for i, w in enumerate(result["warnings"], 1):
            console.print(f"  [yellow]{i}.[/yellow] [bold]{w['title']}[/bold]")
            console.print(f"     {w['comment']}")
            console.print(f"     [dim]Guideline: {w.get('guideline', 'N/A')}[/dim]")

    # Passed
    if result["passed_checks"]:
        console.print("\n[bold green]Passed Checks[/bold green]")
        for p in result["passed_checks"]:
            console.print(f"  [green]✓[/green] {p['title']} — [dim]{p['comment']}[/dim]")

    # Fix list
    console.print("\n[bold]Prioritised Fix List[/bold]")
    fix_table = Table(show_header=True, header_style="bold", show_lines=True)
    fix_table.add_column("#",        width=4)
    fix_table.add_column("Priority", width=10)
    fix_table.add_column("Action",   width=44)
    fix_table.add_column("Effort",   width=8)
    fix_table.add_column("Owner",    width=20)
    for i, f in enumerate(result["fix_list"], 1):
        p = f["priority"]
        col = "red" if p == "P1" else "yellow" if p == "P2" else "green"
        fix_table.add_row(
            str(i),
            f"[{col}]{p}[/{col}]",
            f["action"],
            f.get("effort", ""),
            f.get("owner", "")
        )
    console.print(fix_table)

    if output_file:
        render_plain(result, output_file)


def save_json(result: dict, path: str):
    Path(path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"  JSON saved to: {path}")


# ══════════════════════════════════════════════════════════════════════════════
# 5.  CLI
# ══════════════════════════════════════════════════════════════════════════════

DEMO_CONTENT = """
NDA submission for small molecule oral tablet (twice daily dosing).

Module 1: Cover letter present. Form FDA 356h complete. 
No paediatric investigation plan submitted. Risk Management Plan (RMP) not included.

Module 2: Quality Overall Summary (QOS) drafted but not finalised. 
Non-clinical overview complete. Clinical overview complete.

Module 3: Drug substance — synthesis route described, specifications set, 
3 batches analytical data present. Stability data available for 12 months only 
(accelerated and intermediate conditions). Container closure system described.
Drug product — composition and formulation described, manufacturing process validated, 
finished product specifications set, dissolution data complete.
No comparability protocol for post-approval changes.

Module 4: All non-clinical studies (pharmacology, PK, toxicology) complete and summarised.

Module 5: Pivotal Phase 3 CSR complete. Phase 1/2 data complete. 
No long-term safety update (120-day safety update outstanding).
No dedicated hepatic impairment PK study.
"""


def main():
    parser = argparse.ArgumentParser(
        description="Submission Readiness Scorecard Agent — NDA/MAA dossier reviewer",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="Path to submission plan file (.pdf, .docx, .txt, .md)"
    )
    parser.add_argument(
        "--region", "-r",
        choices=["fda", "ema", "both"],
        default="both",
        help="Target region: fda | ema | both  (default: both)"
    )
    parser.add_argument(
        "--product", "-p",
        choices=["small_molecule", "biologic", "atmp"],
        default="small_molecule",
        help="Product type (default: small_molecule)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Save plain-text report to this file path"
    )
    parser.add_argument(
        "--json",
        type=str,
        default=None,
        help="Save raw JSON result to this file path"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with built-in demo dossier (no file needed)"
    )

    args = parser.parse_args()

    # API key check
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[ERROR] ANTHROPIC_API_KEY environment variable not set.")
        print("  Export it with: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("  SUBMISSION READINESS SCORECARD AGENT")
    print("=" * 70)

    # Load content
    if args.demo:
        print("  Mode     : Demo dossier")
        content = DEMO_CONTENT.strip()
    elif args.file:
        print(f"  File     : {args.file}")
        content = load_submission_file(args.file)
    else:
        # Interactive mode — prompt user
        print("  No file specified. Options:")
        print("    1. Enter a file path")
        print("    2. Paste dossier text directly")
        print("    3. Run demo")
        choice = input("\n  Choice (1/2/3): ").strip()

        if choice == "1":
            file_path = input("  File path: ").strip()
            content = load_submission_file(file_path)
        elif choice == "2":
            print("  Paste your dossier content below. Press Enter twice when done:")
            lines = []
            empty_count = 0
            while empty_count < 2:
                line = input()
                if line == "":
                    empty_count += 1
                else:
                    empty_count = 0
                    lines.append(line)
            content = "\n".join(lines)
        else:
            content = DEMO_CONTENT.strip()

    print(f"  Region   : {args.region.upper()}")
    print(f"  Product  : {args.product.replace('_', ' ').title()}")
    print()

    # Run agent
    try:
        result = run_scorecard(content, args.region, args.product)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Could not parse API response as JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] API call failed: {e}")
        sys.exit(1)

    print()

    # Render output
    if RICH:
        render_rich(result, args.output)
    else:
        render_plain(result, args.output)

    # Save JSON if requested
    if args.json:
        save_json(result, args.json)

    print()


if __name__ == "__main__":
    main()
