#!/usr/bin/env python3
"""PoC-0 Cockpit: Streamlit Dashboard for Defense PoC-0.

Web-based admin dashboard for:
1. System Health Check: Run pytest + scenarios + verify logs
2. Audit Log Explorer: View and filter decision audit logs

Usage:
    streamlit run src/traffic_master_ai/defense/d0_poc/tools/dashboard.py

    Or use the run_dashboard.sh script:
    ./run_dashboard.sh
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

# =============================================================================
# Path Configuration
# =============================================================================

# Project root: go up from tools/dashboard.py to project root
# dashboard.py is at: src/traffic_master_ai/defense/d0_poc/tools/dashboard.py
# So we need to go up 5 levels: tools -> d0_poc -> defense -> traffic_master_ai -> src -> project_root
PROJECT_ROOT = Path(__file__).resolve().parents[5]
LOGS_DIR = PROJECT_ROOT / "logs"
AUDIT_LOG_PATH = LOGS_DIR / "decision_audit.jsonl"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DiagnosticResult:
    """Result of a diagnostic step."""

    step_name: str
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: Optional[float] = None


# =============================================================================
# Session State Keys
# =============================================================================

SESSION_DIAGNOSTICS_RESULTS = "diagnostics_results"
SESSION_DIAGNOSTICS_RUNNING = "diagnostics_running"


def init_session_state() -> None:
    """Initialize session state variables."""
    if SESSION_DIAGNOSTICS_RESULTS not in st.session_state:
        st.session_state[SESSION_DIAGNOSTICS_RESULTS] = []
    if SESSION_DIAGNOSTICS_RUNNING not in st.session_state:
        st.session_state[SESSION_DIAGNOSTICS_RUNNING] = False


# =============================================================================
# Diagnostic Functions
# =============================================================================

def run_command(
    cmd: List[str],
    step_name: str,
    cwd: Path = PROJECT_ROOT,
) -> DiagnosticResult:
    """Run a command and return the result.

    Args:
        cmd: Command and arguments to run.
        step_name: Human-readable name for this step.
        cwd: Working directory.

    Returns:
        DiagnosticResult with success status and output.
    """
    import time

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            env={**dict(__import__("os").environ), "PYTHONPATH": str(PROJECT_ROOT / "src")},
        )
        duration_ms = (time.time() - start_time) * 1000

        return DiagnosticResult(
            step_name=step_name,
            success=(result.returncode == 0),
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired:
        return DiagnosticResult(
            step_name=step_name,
            success=False,
            exit_code=-1,
            stdout="",
            stderr="Command timed out after 300 seconds",
        )
    except Exception as e:
        return DiagnosticResult(
            step_name=step_name,
            success=False,
            exit_code=-1,
            stdout="",
            stderr=str(e),
        )


def run_pytest() -> DiagnosticResult:
    """Run pytest for all D0-1/D0-2/D0-3 tests."""
    return run_command(
        cmd=[sys.executable, "-m", "pytest", "-v", "--tb=short"],
        step_name="Run pytest (D0-1/D0-2/D0-3)",
    )


def run_scenarios() -> DiagnosticResult:
    """Run all acceptance scenarios via run_all.py."""
    return run_command(
        cmd=[
            sys.executable,
            "-m",
            "traffic_master_ai.defense.d0_poc.scenarios.run_all",
        ],
        step_name="Run Acceptance Scenarios (run_all.py)",
    )


def check_logs() -> DiagnosticResult:
    """Check if audit log file exists and has content."""
    step_name = "Verify Audit Logs"

    if not AUDIT_LOG_PATH.exists():
        return DiagnosticResult(
            step_name=step_name,
            success=False,
            exit_code=1,
            stdout="",
            stderr=f"Log file not found: {AUDIT_LOG_PATH}",
        )

    file_size = AUDIT_LOG_PATH.stat().st_size
    line_count = 0

    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            line_count = sum(1 for _ in f)
    except Exception as e:
        return DiagnosticResult(
            step_name=step_name,
            success=False,
            exit_code=1,
            stdout="",
            stderr=f"Error reading log file: {e}",
        )

    stdout = f"Log file: {AUDIT_LOG_PATH}\nSize: {file_size:,} bytes\nEntries: {line_count}"
    return DiagnosticResult(
        step_name=step_name,
        success=True,
        exit_code=0,
        stdout=stdout,
        stderr="",
    )


def run_full_diagnostics() -> List[DiagnosticResult]:
    """Run all diagnostic steps sequentially.

    Returns:
        List of DiagnosticResult for each step.
    """
    results: List[DiagnosticResult] = []

    # Step 1: pytest
    results.append(run_pytest())

    # Step 2: run_all.py
    results.append(run_scenarios())

    # Step 3: verify logs
    results.append(check_logs())

    return results


# =============================================================================
# Log Loading Functions
# =============================================================================

def load_audit_logs() -> Optional[List[Dict[str, Any]]]:
    """Load audit log entries from JSONL file.

    Returns:
        List of log entries, or None if file doesn't exist.
    """
    if not AUDIT_LOG_PATH.exists():
        return None

    entries: List[Dict[str, Any]] = []
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    except Exception:
        return None

    return entries


def entries_to_dataframe(entries: List[Dict[str, Any]]) -> pd.DataFrame:
    """Convert log entries to a pandas DataFrame.

    Column mapping (fixed):
    - Timestamp: entry["ts"]
    - TraceID: entry["trace_id"]
    - Seq: entry["seq"]
    - Event Type: entry["event"]["type"]
    - State: from → to
    - Tier: entry["tier_transition"]["to"]
    - Actions: entry["decision"]["planned_actions"]
    - Reason: terminal_reason or failure_code

    Args:
        entries: List of log entry dictionaries.

    Returns:
        DataFrame with mapped columns.
    """
    rows = []
    for entry in entries:
        event = entry.get("event", {})
        state_trans = entry.get("state_transition", {})
        tier_trans = entry.get("tier_transition", {})
        decision = entry.get("decision", {})

        # Format actions
        actions = decision.get("planned_actions", [])
        actions_str = ", ".join(actions) if actions else None

        # Format reason
        terminal = decision.get("terminal_reason")
        failure = decision.get("failure_code")
        reason = terminal or failure or None

        rows.append({
            "Timestamp": entry.get("ts", ""),
            "TraceID": entry.get("trace_id", ""),
            "Seq": entry.get("seq", 0),
            "Event Type": event.get("type", ""),
            "State": f"{state_trans.get('from', '?')} → {state_trans.get('to', '?')}",
            "Tier": tier_trans.get("to", ""),
            "Actions": actions_str,
            "Reason": reason,
        })

    return pd.DataFrame(rows)


# =============================================================================
# UI Components
# =============================================================================

def render_header() -> None:
    """Render the dashboard header."""
    st.set_page_config(
        page_title="PoC-0 Cockpit",
        page_icon="🛡️",
        layout="wide",
    )

    st.title("🛡️ Traffic Master Defense: PoC-0 Cockpit")
    st.markdown("---")


def render_system_health_section() -> None:
    """Render the System Health Check section."""
    st.header("🔧 System Health Check")

    col1, col2 = st.columns([1, 3])

    with col1:
        if st.button("🚀 Run Full Diagnostics", type="primary", disabled=st.session_state[SESSION_DIAGNOSTICS_RUNNING]):
            st.session_state[SESSION_DIAGNOSTICS_RUNNING] = True
            st.session_state[SESSION_DIAGNOSTICS_RESULTS] = []

            with st.status("Running diagnostics...", expanded=True) as status:
                # Step 1: pytest
                st.write("⏳ Running pytest...")
                result1 = run_pytest()
                st.session_state[SESSION_DIAGNOSTICS_RESULTS].append(result1)
                if result1.success:
                    st.write("✅ pytest passed")
                else:
                    st.write("❌ pytest failed")

                # Step 2: run_all.py
                st.write("⏳ Running acceptance scenarios...")
                result2 = run_scenarios()
                st.session_state[SESSION_DIAGNOSTICS_RESULTS].append(result2)
                if result2.success:
                    st.write("✅ Scenarios passed")
                else:
                    st.write("❌ Scenarios failed")

                # Step 3: check logs
                st.write("⏳ Verifying audit logs...")
                result3 = check_logs()
                st.session_state[SESSION_DIAGNOSTICS_RESULTS].append(result3)
                if result3.success:
                    st.write("✅ Logs verified")
                else:
                    st.write("❌ Log verification failed")

                # Final status
                all_passed = all(r.success for r in st.session_state[SESSION_DIAGNOSTICS_RESULTS])
                if all_passed:
                    status.update(label="✅ All diagnostics passed!", state="complete", expanded=False)
                else:
                    status.update(label="❌ Some diagnostics failed", state="error", expanded=True)

            st.session_state[SESSION_DIAGNOSTICS_RUNNING] = False
            st.rerun()

    # Display results if available
    results = st.session_state[SESSION_DIAGNOSTICS_RESULTS]
    if results:
        st.subheader("Diagnostic Results")

        for result in results:
            icon = "✅" if result.success else "❌"
            with st.expander(f"{icon} {result.step_name} (exit code: {result.exit_code})", expanded=not result.success):
                if result.duration_ms:
                    st.caption(f"Duration: {result.duration_ms:.0f}ms")

                if result.stdout:
                    st.text("STDOUT:")
                    st.code(result.stdout, language="text")

                if result.stderr:
                    st.text("STDERR:")
                    st.code(result.stderr, language="text")

    st.markdown("---")


def render_audit_log_explorer() -> None:
    """Render the Audit Log Explorer section."""
    st.header("📊 Audit Log Explorer")

    entries = load_audit_logs()

    if entries is None or len(entries) == 0:
        st.warning("⚠️ No logs found. Run validation first.")
        st.info(f"Expected log file: `{AUDIT_LOG_PATH}`")
        return

    # Convert to DataFrame
    df = entries_to_dataframe(entries)

    # Filter controls
    st.subheader("Filters")
    col1, col2 = st.columns(2)

    with col1:
        # TraceID dropdown
        trace_ids = ["All"] + sorted(df["TraceID"].unique().tolist())
        selected_trace = st.selectbox("Filter by TraceID", trace_ids)

    with col2:
        # Tier filter
        tiers = ["All"] + sorted(df["Tier"].unique().tolist())
        selected_tier = st.selectbox("Filter by Tier", tiers)

    # Apply filters
    filtered_df = df.copy()
    if selected_trace != "All":
        filtered_df = filtered_df[filtered_df["TraceID"] == selected_trace]
    if selected_tier != "All":
        filtered_df = filtered_df[filtered_df["Tier"] == selected_tier]

    # Display stats
    st.subheader("Summary")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Entries", len(filtered_df))
    with col2:
        st.metric("Unique Traces", filtered_df["TraceID"].nunique())
    with col3:
        st.metric("T3 Escalations", len(filtered_df[filtered_df["Tier"] == "T3"]))
    with col4:
        blocked_count = len(filtered_df[filtered_df["Reason"] == "BLOCKED"])
        st.metric("Blocked Sessions", blocked_count)

    # Display table
    st.subheader("Log Entries")
    st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Timestamp": st.column_config.TextColumn("Timestamp", width="medium"),
            "TraceID": st.column_config.TextColumn("TraceID", width="small"),
            "Seq": st.column_config.NumberColumn("Seq", width="small"),
            "Event Type": st.column_config.TextColumn("Event Type", width="medium"),
            "State": st.column_config.TextColumn("State", width="small"),
            "Tier": st.column_config.TextColumn("Tier", width="small"),
            "Actions": st.column_config.TextColumn("Actions", width="medium"),
            "Reason": st.column_config.TextColumn("Reason", width="medium"),
        },
    )

    # Raw JSON viewer for selected trace
    if selected_trace != "All":
        st.subheader(f"Raw JSON for {selected_trace}")
        trace_entries = [e for e in entries if e.get("trace_id") == selected_trace]
        st.json(trace_entries)


def render_footer() -> None:
    """Render the dashboard footer."""
    st.markdown("---")
    st.caption(
        f"📁 Project Root: `{PROJECT_ROOT}`  \n"
        f"📄 Log File: `{AUDIT_LOG_PATH}`"
    )


# =============================================================================
# Main Entry Point
# =============================================================================

def main() -> None:
    """Main entry point for the dashboard."""
    init_session_state()
    render_header()
    render_system_health_section()
    render_audit_log_explorer()
    render_footer()


if __name__ == "__main__":
    main()
