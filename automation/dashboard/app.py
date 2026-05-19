from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
import time

import streamlit as st

from dashboard.cli_builder import DashboardRunOptions, build_crawler_command
from dashboard.file_views import (
    list_yaml_profiles,
    load_recent_urls,
    read_checkpoint,
    read_jsonl_tail,
    save_recent_url,
)
from dashboard.process_manager import DashboardProcessManager

AUTOMATION_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = AUTOMATION_DIR / "output"
BASE_PROFILES_DIR = AUTOMATION_DIR / "profiles"
LEARNED_PROFILES_DIR = BASE_PROFILES_DIR / "domains"
DEFAULT_DASHBOARD_MODEL = os.getenv("MCQ_DASHBOARD_MODEL", "gpt-5.4")


@st.cache_resource
def get_process_manager() -> DashboardProcessManager:
    return DashboardProcessManager()


def render_log_text() -> str:
    manager = get_process_manager()
    events = manager.get_logs(limit=500)
    lines: list[str] = []
    for event in events:
        lines.append(f"[{event.timestamp}][{event.stream}] {event.text}")
    return "\n".join(lines)


def profile_label(profile: Path | None) -> str:
    if profile is None:
        return "(default profile logic)"
    try:
        return str(profile.relative_to(AUTOMATION_DIR))
    except ValueError:
        return profile.name


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"

    total_seconds = max(0, int(seconds))
    hours, rem = divmod(total_seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def main() -> None:
    st.set_page_config(page_title="MCQ Crawler Dashboard", layout="wide")
    st.title("MCQ Crawler Personal Dashboard")
    st.caption("Thin local dashboard. CLI remains the execution engine.")

    manager = get_process_manager()
    manager.poll_logs()

    recent_urls = load_recent_urls(OUTPUT_DIR)
    base_profiles, learned_profiles = list_yaml_profiles(
        BASE_PROFILES_DIR,
        LEARNED_PROFILES_DIR,
        workspace_root=AUTOMATION_DIR,
    )

    if "start_url" not in st.session_state:
        st.session_state.start_url = recent_urls[0] if recent_urls else ""
    if "last_run_summary" not in st.session_state:
        st.session_state.last_run_summary = None

    st.sidebar.header("Run Controls")
    chosen_recent = st.sidebar.selectbox(
        "Recent URL",
        options=["(none)", *recent_urls],
        index=0,
    )
    if chosen_recent != "(none)":
        st.session_state.start_url = chosen_recent

    start_url = st.sidebar.text_input("Start URL", key="start_url")

    profile_choices: list[Path | None] = [None, *base_profiles, *learned_profiles]
    selected_profile = st.sidebar.selectbox(
        "Profile",
        options=profile_choices,
        format_func=profile_label,
    )

    resume = st.sidebar.checkbox("Resume from checkpoint", value=True)
    headless = st.sidebar.checkbox("Headless", value=False)
    selector_debug = st.sidebar.checkbox("Selector debug", value=False)
    require_answers = st.sidebar.checkbox("Require answers", value=True)
    auto_learn_profiles = st.sidebar.checkbox("Auto learn profiles", value=True)

    max_records = st.sidebar.number_input("Max records", min_value=1, max_value=5000, value=200)
    max_turns = st.sidebar.number_input("Max turns", min_value=10, max_value=10000, value=800)
    start_index = st.sidebar.number_input("Start index", min_value=1, max_value=100000, value=1)
    min_confidence = st.sidebar.number_input("Min confidence", min_value=0.0, max_value=1.0, value=0.65, step=0.01)
    min_quality_score = st.sidebar.number_input("Min quality score", min_value=0.0, max_value=1.0, value=0.72, step=0.01)
    model = st.sidebar.text_input("Model", value=DEFAULT_DASHBOARD_MODEL)
    st.sidebar.caption(
        "Use a model available in your Copilot account (default: gpt-5.4)."
    )

    run_col, stop_col, refresh_col = st.columns([1, 1, 1])

    with run_col:
        if st.button("Start run", type="primary", use_container_width=True):
            if not start_url.strip():
                st.error("Start URL is required.")
            else:
                profile_path = str(selected_profile) if selected_profile is not None else None

                options = DashboardRunOptions(
                    start_url=start_url.strip(),
                    profile_path=profile_path,
                    resume=resume,
                    headless=headless,
                    max_records=int(max_records),
                    max_turns=int(max_turns),
                    start_index=int(start_index),
                    min_confidence=float(min_confidence),
                    min_quality_score=float(min_quality_score),
                    require_answers=require_answers,
                    auto_learn_profiles=auto_learn_profiles,
                    selector_debug=selector_debug,
                    model=model.strip() or "gpt-5",
                )
                command = build_crawler_command(AUTOMATION_DIR, options)
                ok, message = manager.start(command, cwd=AUTOMATION_DIR)
                if ok:
                    save_recent_url(OUTPUT_DIR, options.start_url)
                    st.session_state.last_run_summary = {
                        "url": options.start_url,
                        "profile": (
                            profile_label(selected_profile)
                            if selected_profile is not None
                            else "default profile logic"
                        ),
                        "max_records": options.max_records,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "command": shlex.join(command),
                        "stopped_at": "",
                    }
                    manager.add_local_log(f"Selected URL: {options.start_url}")
                    manager.add_local_log(
                        "Selected profile: "
                        + (
                            profile_label(selected_profile)
                            if selected_profile is not None
                            else "default profile logic"
                        ),
                    )
                    st.success(message)
                else:
                    st.warning(message)

                st.code(shlex.join(command), language="bash")

    with stop_col:
        if st.button("Stop run", use_container_width=True):
            ok, message = manager.stop()
            if ok:
                summary = st.session_state.get("last_run_summary")
                if summary:
                    summary["stopped_at"] = datetime.now(timezone.utc).isoformat()
                st.success(message)
            else:
                st.warning(message)

    with refresh_col:
        if st.button("Refresh now", use_container_width=True):
            manager.poll_logs()
            st.rerun()

    status = manager.status()
    code = manager.return_code()
    st.info(f"Process status: {status} | Return code: {code}")

    checkpoint_path = OUTPUT_DIR / "checkpoint.json"
    checkpoint = read_checkpoint(checkpoint_path)

    current_page_index = _as_int(checkpoint.get("next_index")) if isinstance(checkpoint, dict) else None
    records_written = _as_int(checkpoint.get("records_written")) if isinstance(checkpoint, dict) else None
    target_records = _as_int(checkpoint.get("max_records")) if isinstance(checkpoint, dict) else None
    current_page_candidates_found = _as_int(checkpoint.get("current_page_candidates_found")) if isinstance(checkpoint, dict) else None
    current_page_saved = _as_int(checkpoint.get("current_page_saved")) if isinstance(checkpoint, dict) else None
    current_page_skipped = _as_int(checkpoint.get("current_page_skipped")) if isinstance(checkpoint, dict) else None
    last_page_candidates_found = _as_int(checkpoint.get("last_page_candidates_found")) if isinstance(checkpoint, dict) else None
    last_page_saved = _as_int(checkpoint.get("last_page_saved")) if isinstance(checkpoint, dict) else None
    last_page_skipped = _as_int(checkpoint.get("last_page_skipped")) if isinstance(checkpoint, dict) else None
    pages_processed = _as_int(checkpoint.get("pages_processed")) if isinstance(checkpoint, dict) else None

    summary = st.session_state.get("last_run_summary")
    if target_records is None and isinstance(summary, dict):
        target_records = _as_int(summary.get("max_records"))

    now_epoch = time.time()

    run_started_at_epoch = (
        _as_float(checkpoint.get("run_started_at_epoch"))
        if isinstance(checkpoint, dict)
        else None
    )
    page_started_at_epoch = (
        _as_float(checkpoint.get("page_started_at_epoch"))
        if isinstance(checkpoint, dict)
        else None
    )

    run_elapsed = (
        _format_duration(now_epoch - run_started_at_epoch)
        if run_started_at_epoch is not None
        else "-"
    )
    page_elapsed = (
        _format_duration(now_epoch - page_started_at_epoch)
        if page_started_at_epoch is not None
        else "-"
    )

    avg_seconds_per_page: float | None = None
    if run_started_at_epoch is not None and records_written is not None and records_written > 0:
        avg_seconds_per_page = max(0.0, now_epoch - run_started_at_epoch) / records_written

    avg_page_elapsed = _format_duration(avg_seconds_per_page)

    eta_remaining = "-"
    if avg_seconds_per_page is not None and target_records is not None and records_written is not None:
        remaining_records = max(0, target_records - records_written)
        eta_remaining = _format_duration(avg_seconds_per_page * remaining_records)

    st.subheader("Live progress")
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("Current page index", str(current_page_index) if current_page_index is not None else "-")
    p2.metric("Run elapsed", run_elapsed)
    p3.metric("Current page elapsed", page_elapsed)
    p4.metric("Avg time per page", avg_page_elapsed)
    p5.metric("ETA remaining", eta_remaining)

    st.caption("Page extraction counters")
    pc1, pc2, pc3, pc4 = st.columns(4)
    pc1.metric(
        "Current page (found/saved/skipped)",
        (
            f"{current_page_candidates_found or 0}/{current_page_saved or 0}/{current_page_skipped or 0}"
            if any(value is not None for value in [current_page_candidates_found, current_page_saved, current_page_skipped])
            else "-"
        ),
    )
    pc2.metric(
        "Last page (found/saved/skipped)",
        (
            f"{last_page_candidates_found or 0}/{last_page_saved or 0}/{last_page_skipped or 0}"
            if any(value is not None for value in [last_page_candidates_found, last_page_saved, last_page_skipped])
            else "-"
        ),
    )
    pc3.metric("Pages processed", str(pages_processed) if pages_processed is not None else "-")
    pc4.metric(
        "Current page yield",
        (
            f"{current_page_saved}/{current_page_candidates_found}"
            if current_page_saved is not None and current_page_candidates_found not in (None, 0)
            else "-"
        ),
    )

    recent_logs = manager.get_logs(limit=120)
    model_error = None
    for event in recent_logs:
        if "is not available" in event.text and "Model" in event.text:
            model_error = event.text
            break
    if model_error:
        st.error(
            "Selected model is not available for this account. "
            "Change the Model field to an available model (for example gpt-5.4) and start the run again."
        )
        st.caption(model_error)

    if summary:
        if status in {"completed", "failed"} and not summary.get("stopped_at"):
            summary["stopped_at"] = datetime.now(timezone.utc).isoformat()

        st.subheader("Current run summary")
        c1, c2, c3 = st.columns(3)
        c1.metric("Status", status)
        c2.metric("Started", summary.get("started_at", ""))
        c3.metric("Stopped", summary.get("stopped_at", "-") or "-")
        st.write(f"URL: {summary.get('url', '')}")
        st.write(f"Profile: {summary.get('profile', '')}")
        st.caption("Command")
        st.code(summary.get("command", ""), language="bash")

    st.subheader("Manual input bridge")
    st.caption(
        "Use this when the crawler asks for intervention input, or click a named quick action."
    )
    manual_value = st.text_input("Send input to running process", value="", key="manual_value")

    send_col, c_col, o_col, s_col, q_col = st.columns([2, 1.4, 1.4, 1.2, 1.2])
    with send_col:
        if st.button("Send input", use_container_width=True):
            ok, message = manager.send_input(manual_value)
            if ok:
                st.success(message)
                st.session_state.manual_value = ""
            else:
                st.warning(message)

    quick_actions = [
        (c_col, "Captcha Solved", "c"),
        (o_col, "Override", "o"),
        (s_col, "Skip Next", "s"),
        (q_col, "Quit", "q"),
    ]
    for column, label, value in quick_actions:
        with column:
            if st.button(label, use_container_width=True):
                ok, message = manager.send_input(value)
                if ok:
                    st.success(f"Sent {label}")
                else:
                    st.warning(message)

    st.subheader("Live process logs")
    st.text_area("stdout/stderr", value=render_log_text(), height=320)

    records_path = OUTPUT_DIR / "records.jsonl"
    errors_path = OUTPUT_DIR / "errors.jsonl"
    debug_path = OUTPUT_DIR / "selector_debug.jsonl"
    tab_records, tab_errors, tab_debug, tab_checkpoint, tab_profiles = st.tabs(
        ["Records", "Errors", "Selector debug", "Checkpoint", "Profiles"],
    )

    with tab_records:
        records = read_jsonl_tail(records_path, max_lines=150)
        st.caption(f"Showing last {len(records)} record lines from {records_path}")
        st.json(records[-20:] if len(records) > 20 else records)

    with tab_errors:
        errors = read_jsonl_tail(errors_path, max_lines=150)
        st.caption(f"Showing last {len(errors)} error lines from {errors_path}")
        st.json(errors[-20:] if len(errors) > 20 else errors)

    with tab_debug:
        debug_events = read_jsonl_tail(debug_path, max_lines=150)
        st.caption(f"Showing last {len(debug_events)} debug lines from {debug_path}")
        st.json(debug_events[-20:] if len(debug_events) > 20 else debug_events)

    with tab_checkpoint:
        st.caption(f"Checkpoint file: {checkpoint_path}")
        st.json(checkpoint)

    with tab_profiles:
        st.markdown("Base profiles")
        st.json([profile_label(item) for item in base_profiles])
        st.markdown("Learned domain profiles")
        st.json([profile_label(item) for item in learned_profiles])

    auto_refresh = st.checkbox("Auto refresh while running", value=True)
    refresh_seconds = st.slider("Refresh interval (seconds)", min_value=1, max_value=10, value=2)

    if auto_refresh and manager.is_running():
        time.sleep(refresh_seconds)
        st.rerun()


if __name__ == "__main__":
    main()
