#!/usr/bin/env python3
"""Log Analyzer & CLI Replay Reporter for Defense PoC-0.

Parses poc_0_decision_audit.jsonl and provides:
1. Summary Report: Overview of all scenarios by trace_id
2. Detail Replay: Step-by-step timeline for a specific scenario

Usage:
    # Summary Report (default)
    python -m traffic_master_ai.defense.d0_poc.tools.analyze_logs

    # Detail Replay for specific scenario
    python -m traffic_master_ai.defense.d0_poc.tools.analyze_logs --id SCN-08

    # Custom log path
    python -m traffic_master_ai.defense.d0_poc.tools.analyze_logs --log-path /path/to/audit.jsonl

    # Disable ANSI colors
    python -m traffic_master_ai.defense.d0_poc.tools.analyze_logs --no-color
"""

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional


# =============================================================================
# ANSI Color Codes
# =============================================================================

class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"

    # Foreground colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Background colors
    BG_RED = "\033[41m"
    BG_YELLOW = "\033[43m"


class ColorPrinter:
    """Handles colored terminal output with optional disable."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def _wrap(self, text: str, *codes: str) -> str:
        """Wrap text with color codes if enabled."""
        if not self.enabled:
            return text
        return "".join(codes) + text + Colors.RESET

    def bold(self, text: str) -> str:
        return self._wrap(text, Colors.BOLD)

    def red(self, text: str) -> str:
        return self._wrap(text, Colors.RED)

    def green(self, text: str) -> str:
        return self._wrap(text, Colors.GREEN)

    def yellow(self, text: str) -> str:
        return self._wrap(text, Colors.YELLOW)

    def cyan(self, text: str) -> str:
        return self._wrap(text, Colors.CYAN)

    def highlight_danger(self, text: str) -> str:
        """Highlight with red background for critical items."""
        return self._wrap(text, Colors.BOLD, Colors.RED)

    def highlight_warn(self, text: str) -> str:
        """Highlight with yellow for warnings."""
        return self._wrap(text, Colors.BOLD, Colors.YELLOW)


# =============================================================================
# Log Parser
# =============================================================================

def load_log_entries(log_path: Path) -> List[Dict[str, Any]]:
    """Load and parse JSONL log file.

    Args:
        log_path: Path to the JSONL file.

    Returns:
        List of parsed log entries.

    Raises:
        FileNotFoundError: If log file doesn't exist.
        ValueError: If a line cannot be parsed.
    """
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    entries: List[Dict[str, Any]] = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entries.append(entry)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON at line {line_num}: {e}")

    return entries


def group_by_trace(entries: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group log entries by trace_id.

    Args:
        entries: List of log entries.

    Returns:
        OrderedDict of trace_id -> list of entries (preserves insertion order).
    """
    grouped: Dict[str, List[Dict[str, Any]]] = OrderedDict()
    for entry in entries:
        trace_id = entry.get("trace_id", "UNKNOWN")
        if trace_id not in grouped:
            grouped[trace_id] = []
        grouped[trace_id].append(entry)

    # Sort entries within each trace by seq
    for trace_id in grouped:
        grouped[trace_id].sort(key=lambda e: e.get("seq", 0))

    return grouped


# =============================================================================
# Summary Report
# =============================================================================

def print_summary_report(
    grouped: Dict[str, List[Dict[str, Any]]],
    color: ColorPrinter,
) -> None:
    """Print summary table of all scenarios.

    Args:
        grouped: Entries grouped by trace_id.
        color: ColorPrinter instance.
    """
    # Fixed column widths
    col_id = 12
    col_steps = 7
    col_state = 8
    col_tier = 6
    col_terminal = 20

    total_width = col_id + col_steps + col_state + col_tier + col_terminal + 12

    # Header
    print()
    print(color.bold("=" * total_width))
    print(color.bold("Defense PoC-0 Decision Log Summary"))
    print(color.bold("=" * total_width))
    print()

    # Table header
    header = (
        f"{'Scenario ID':<{col_id}} | "
        f"{'Steps':>{col_steps}} | "
        f"{'Final':^{col_state}} | "
        f"{'Tier':^{col_tier}} | "
        f"{'Terminal Reason':<{col_terminal}}"
    )
    print(color.cyan(header))
    print("-" * total_width)

    # Rows
    for trace_id, entries in grouped.items():
        total_steps = len(entries)
        last_entry = entries[-1]

        final_state = last_entry.get("state_transition", {}).get("to", "?")
        final_tier = last_entry.get("tier_transition", {}).get("to", "?")
        terminal_reason = last_entry.get("decision", {}).get("terminal_reason")

        # Highlight critical states
        state_str = final_state
        if final_state == "SX":
            state_str = color.highlight_danger(final_state)

        terminal_str = str(terminal_reason) if terminal_reason else "-"
        if terminal_reason:
            terminal_str = color.yellow(terminal_str)

        row = (
            f"{trace_id:<{col_id}} | "
            f"{total_steps:>{col_steps}} | "
            f"{state_str:^{col_state}} | "
            f"{final_tier:^{col_tier}} | "
            f"{terminal_str:<{col_terminal}}"
        )
        print(row)

    print("-" * total_width)
    print(f"Total scenarios: {len(grouped)}, Total steps: {sum(len(e) for e in grouped.values())}")
    print("=" * total_width)
    print()


# =============================================================================
# Detail Replay
# =============================================================================

def print_detail_replay(
    trace_id: str,
    entries: List[Dict[str, Any]],
    color: ColorPrinter,
) -> None:
    """Print detailed step-by-step replay for a specific scenario.

    Args:
        trace_id: The trace ID to replay.
        entries: List of log entries for this trace.
        color: ColorPrinter instance.
    """
    print()
    print(color.bold("=" * 80))
    print(color.bold(f"Detail Replay: {trace_id}"))
    print(color.bold("=" * 80))
    print()

    # Column widths for detail view
    col_seq = 4
    col_event = 28
    col_state = 12
    col_tier = 10
    col_actions = 18
    col_terminal = 15

    # Header
    header = (
        f"{'Seq':>{col_seq}} | "
        f"{'Event Type':<{col_event}} | "
        f"{'State':^{col_state}} | "
        f"{'Tier':^{col_tier}} | "
        f"{'Actions':<{col_actions}} | "
        f"{'Terminal':<{col_terminal}}"
    )
    print(color.cyan(header))
    print("-" * 100)

    for entry in entries:
        seq = entry.get("seq", "?")
        event_type = entry.get("event", {}).get("type", "?")

        state_from = entry.get("state_transition", {}).get("from", "?")
        state_to = entry.get("state_transition", {}).get("to", "?")
        tier_from = entry.get("tier_transition", {}).get("from", "?")
        tier_to = entry.get("tier_transition", {}).get("to", "?")

        decision = entry.get("decision", {})
        planned_actions = decision.get("planned_actions", [])
        terminal_reason = decision.get("terminal_reason")
        failure_code = decision.get("failure_code")

        # Format state transition
        state_str = f"{state_from}→{state_to}"

        # Highlight SX state
        if state_to == "SX":
            state_str = color.highlight_danger(state_str)

        # Format tier transition
        tier_str = f"{tier_from}→{tier_to}"
        if tier_from != tier_to:
            tier_str = color.yellow(tier_str)

        # Format actions
        actions_str = ",".join(planned_actions) if planned_actions else "-"
        if any("BLOCK" in a for a in planned_actions):
            actions_str = color.highlight_danger(actions_str)
        elif planned_actions:
            actions_str = color.green(actions_str)

        # Format terminal/failure
        terminal_str = "-"
        if terminal_reason:
            terminal_str = terminal_reason
            terminal_str = color.yellow(terminal_str)
        if failure_code:
            terminal_str = f"{terminal_reason or '?'}/{failure_code}"
            terminal_str = color.red(terminal_str)

        # Truncate long strings
        event_display = event_type[:col_event]
        actions_display = actions_str[:col_actions] if len(actions_str) > col_actions else actions_str

        row = (
            f"{seq:>{col_seq}} | "
            f"{event_display:<{col_event}} | "
            f"{state_str:^{col_state}} | "
            f"{tier_str:^{col_tier}} | "
            f"{actions_display:<{col_actions}} | "
            f"{terminal_str:<{col_terminal}}"
        )
        print(row)

    print("-" * 100)
    print(f"Total steps: {len(entries)}")
    print("=" * 80)
    print()


# =============================================================================
# Main Entry Point
# =============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Defense PoC-0 Log Analyzer & CLI Replay Reporter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show summary of all scenarios
  python -m traffic_master_ai.defense.d0_poc.tools.analyze_logs

  # Show detailed replay for SCN-08
  python -m traffic_master_ai.defense.d0_poc.tools.analyze_logs --id SCN-08

  # Use custom log file
  python -m traffic_master_ai.defense.d0_poc.tools.analyze_logs --log-path ./my_logs/audit.jsonl
        """,
    )

    parser.add_argument(
        "--log-path",
        type=str,
        default="logs/poc_0_decision_audit.jsonl",
        help="Path to JSONL log file (default: logs/poc_0_decision_audit.jsonl)",
    )

    parser.add_argument(
        "--id",
        type=str,
        dest="trace_id",
        default=None,
        help="Specific trace_id (scenario ID) to show detailed replay",
    )

    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color output",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point.

    Returns:
        0 on success, 1 on error.
    """
    args = parse_args()

    # Initialize color printer
    color = ColorPrinter(enabled=not args.no_color)

    # Resolve log path
    log_path = Path(args.log_path)

    # Load entries
    try:
        entries = load_log_entries(log_path)
    except FileNotFoundError as e:
        print(color.red(f"Error: {e}"))
        print(f"Hint: Run 'python -m traffic_master_ai.defense.d0_poc.scenarios.run_all' first to generate logs.")
        return 1
    except ValueError as e:
        print(color.red(f"Error: {e}"))
        return 1

    if not entries:
        print(color.yellow("Warning: Log file is empty."))
        return 0

    # Group by trace_id
    grouped = group_by_trace(entries)

    # Handle specific trace_id replay
    if args.trace_id:
        if args.trace_id not in grouped:
            print(color.red(f"Error: trace_id '{args.trace_id}' not found in logs."))
            print(f"Available trace_ids: {', '.join(grouped.keys())}")
            return 1
        print_detail_replay(args.trace_id, grouped[args.trace_id], color)
    else:
        # Default: summary report
        print_summary_report(grouped, color)

    return 0


if __name__ == "__main__":
    sys.exit(main())
