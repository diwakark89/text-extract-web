from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
import sys
import time

import streamlit as st

AUTOMATION_DIR = Path(__file__).resolve().parents[1]
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from dashboard.cli_builder import (
    DashboardRunOptions,
    build_crawler_command,
    resolve_records_output_path,
)
from dashboard.file_views import (
    list_yaml_profiles,
    load_profile_for_url,
    load_recent_urls,
    read_checkpoint,
    read_jsonl_tail,
    save_profile_for_url,
    save_recent_url,
    url_host_key,
)
from dashboard.process_manager import DashboardProcessManager

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
    if "recent_url_selector" not in st.session_state:
        st.session_state.recent_url_selector = "(none)"
    if "last_applied_recent_url" not in st.session_state:
        st.session_state.last_applied_recent_url = ""
    if "last_run_summary" not in st.session_state:
        st.session_state.last_run_summary = None
    if "selected_profile_path" not in st.session_state:
        remembered = load_profile_for_url(OUTPUT_DIR, st.session_state.start_url)
        st.session_state.selected_profile_path = remembered or ""
    if "profile_host_key" not in st.session_state:
        st.session_state.profile_host_key = url_host_key(st.session_state.start_url)

    st.sidebar.header("Run Controls")
    chosen_recent = st.sidebar.selectbox(
        "Recent URL",
        options=["(none)", *recent_urls],
        index=0,
        key="recent_url_selector",
    )
    if chosen_recent != "(none)" and chosen_recent != st.session_state.last_applied_recent_url:
        st.session_state.start_url = chosen_recent
        st.session_state.last_applied_recent_url = chosen_recent

    start_url = st.sidebar.text_input("Start URL", key="start_url")

    current_host = url_host_key(start_url)
    if st.session_state.get("profile_host_key") != current_host:
        remembered_profile = load_profile_for_url(OUTPUT_DIR, start_url)
        st.session_state.selected_profile_path = remembered_profile or ""
        st.session_state.profile_host_key = current_host
    else:
        remembered_profile = load_profile_for_url(OUTPUT_DIR, start_url)

    profile_choices: list[Path | None] = [None, *base_profiles, *learned_profiles]

    def _profile_value(profile: Path | None) -> str:
        if profile is None:
            return ""
        return str(profile.resolve())

    profile_by_value = {_profile_value(profile): profile for profile in profile_choices}
    profile_values = list(profile_by_value.keys())
    selected_profile_value = str(st.session_state.get("selected_profile_path") or "").strip()
    if selected_profile_value not in profile_values:
        selected_profile_value = ""

    selected_profile_value = st.sidebar.selectbox(
        "Profile",
        options=profile_values,
        index=profile_values.index(selected_profile_value),
        format_func=lambda value: profile_label(profile_by_value.get(value)),
    )
    st.session_state.selected_profile_path = selected_profile_value

    remembered_profile_value = str(remembered_profile or "").strip()
    if current_host and selected_profile_value != remembered_profile_value:
        save_profile_for_url(
            OUTPUT_DIR,
            start_url,
            (selected_profile_value or None),
        )

    selected_profile = profile_by_value.get(selected_profile_value)

    resume = st.sidebar.checkbox("Resume from checkpoint", value=True)
    headless = st.sidebar.checkbox("Headless", value=False)
    prompt_for_login_at_start = st.sidebar.checkbox(
        "Prompt for login at start",
        value=False,
        help="Open page and wait for manual login before crawling starts.",
    )
    enable_auto_login = st.sidebar.checkbox(
        "Auto login from auth file",
        value=False,
        help="Use host-based credentials/selectors from a local auth YAML before manual prompt.",
    )
    auth_file_path = st.sidebar.text_input(
        "Auth file",
        value="auth/auth_hosts.yaml",
        help="Path to local host auth YAML (kept out of git).",
    )
    auto_login_timeout_seconds = st.sidebar.number_input(
        "Auto login timeout (sec)",
        min_value=5,
        max_value=300,
        value=40,
        step=1,
    )
    selector_debug = st.sidebar.checkbox("Selector debug", value=False)
    require_answers = st.sidebar.checkbox("Require answers", value=True)
    stop_on_missing_answers = st.sidebar.checkbox("Stop if answers missing", value=True)
    auto_learn_profiles = st.sidebar.checkbox("Auto learn profiles", value=True)
    records_output_name = st.sidebar.text_input(
        "Records file name",
        value="records.jsonl",
        help="Use .jsonl or .json. If .json is entered, crawler writes .jsonl and maintains a matching .json mirror.",
    )
    st.session_state.records_output_name = records_output_name.strip() or "records.jsonl"

    max_records = st.sidebar.number_input("Max records", min_value=1, max_value=5000, value=200)
    max_turns = st.sidebar.number_input("Max turns", min_value=10, max_value=10000, value=800)
    start_index = st.sidebar.number_input("Start index", min_value=1, max_value=100000, value=1)
    min_confidence = st.sidebar.number_input("Min confidence", min_value=0.0, max_value=1.0, value=0.65, step=0.01)
    min_quality_score = st.sidebar.number_input("Min quality score", min_value=0.0, max_value=1.0, value=0.72, step=0.01)
    model = st.sidebar.text_input("Model", value=DEFAULT_DASHBOARD_MODEL)
    orchestration_mode = st.sidebar.selectbox(
        "Orchestration mode",
        options=["hybrid_gap_fill", "deterministic_only", "llm_orchestrator"],
        index=0,
        help="hybrid_gap_fill uses deterministic crawling and invokes Copilot only on extraction gaps.",
    )
    st.sidebar.caption(
        "Use a model available in your Copilot account (default: gpt-5.4)."
    )

    run_col, stop_col, refresh_col = st.columns([1, 1, 1])

    with run_col:
        if st.button("Start run", type="primary", use_container_width=True):
            if not start_url.strip():
                st.error("Start URL is required.")
            else:
                profile_path = str(selected_profile.resolve()) if selected_profile is not None else None

                options = DashboardRunOptions(
                    start_url=start_url.strip(),
                    profile_path=profile_path,
                    orchestration_mode=orchestration_mode,
                    resume=resume,
                    headless=headless,
                    max_records=int(max_records),
                    max_turns=int(max_turns),
                    start_index=int(start_index),
                    min_confidence=float(min_confidence),
                    min_quality_score=float(min_quality_score),
                    require_answers=require_answers,
                    stop_on_missing_answers=stop_on_missing_answers,
                    auto_learn_profiles=auto_learn_profiles,
                    selector_debug=selector_debug,
                    records_output_name=(records_output_name.strip() or "records.jsonl"),
                    model=model.strip() or "gpt-5",
                    prompt_for_login_at_start=prompt_for_login_at_start,
                    enable_auto_login=enable_auto_login,
                    auth_file_path=auth_file_path.strip() or "auth/auth_hosts.yaml",
                    auto_login_timeout_seconds=int(auto_login_timeout_seconds),
                )

                # Avoid accidentally resuming into an old checkpoint URL when user entered a new URL.
                resume_checkpoint = read_checkpoint(OUTPUT_DIR / "checkpoint.json")
                checkpoint_current_url = str(resume_checkpoint.get("current_url") or "").strip()
                if options.resume and checkpoint_current_url and checkpoint_current_url != options.start_url:
                    options.resume = False
                    st.warning(
                        "Resume was disabled for this run because checkpoint URL differs from Start URL. "
                        "Use the same URL as checkpoint if you want to continue that previous run."
                    )

                command = build_crawler_command(AUTOMATION_DIR, options)
                ok, message = manager.start(command, cwd=AUTOMATION_DIR)
                if ok:
                    save_recent_url(OUTPUT_DIR, options.start_url)
                    save_profile_for_url(OUTPUT_DIR, options.start_url, profile_path)
                    st.session_state.profile_host_key = url_host_key(options.start_url)
                    st.session_state.selected_profile_path = profile_path or ""
                    st.session_state.last_run_summary = {
                        "url": options.start_url,
                        "profile": (
                            profile_label(selected_profile)
                            if selected_profile is not None
                            else "default profile logic"
                        ),
                        "max_records": options.max_records,
                        "stop_on_missing_answers": options.stop_on_missing_answers,
                        "records_output_path": str(
                            resolve_records_output_path(AUTOMATION_DIR, options.records_output_name)
                        ),
                        "prompt_for_login_at_start": options.prompt_for_login_at_start,
                        "enable_auto_login": options.enable_auto_login,
                        "auth_file_path": options.auth_file_path,
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

    current_page_llm_assists = _as_int(checkpoint.get("current_page_llm_assists")) if isinstance(checkpoint, dict) else None
    llm_assist_attempts_total = _as_int(checkpoint.get("llm_assist_attempts_total")) if isinstance(checkpoint, dict) else None
    llm_assist_saved_count = _as_int(checkpoint.get("llm_assist_saved_count")) if isinstance(checkpoint, dict) else None
    llm_assist_last_trigger_reason = (
        str(checkpoint.get("llm_assist_last_trigger_reason") or "").strip()
        if isinstance(checkpoint, dict)
        else ""
    )

    summary = st.session_state.get("last_run_summary")

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
        s1, s2, s3 = st.columns(3)
        s1.metric("Assist attempts", str(llm_assist_attempts_total or 0))
        s2.metric("Assist saves", str(llm_assist_saved_count or 0))
        s3.metric("Current page assists", str(current_page_llm_assists or 0))
        st.write(f"URL: {summary.get('url', '')}")
        st.write(f"Profile: {summary.get('profile', '')}")
        st.write(
            "Last assist trigger reason: "
            + (llm_assist_last_trigger_reason if llm_assist_last_trigger_reason else "-")
        )
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
        (c_col, "Continue", "c"),
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

    default_records_path = resolve_records_output_path(
        AUTOMATION_DIR,
        str(st.session_state.get("records_output_name") or "records.jsonl"),
    )
    summary_records_path = (
        Path(str(summary.get("records_output_path") or "").strip())
        if isinstance(summary, dict) and str(summary.get("records_output_path") or "").strip()
        else default_records_path
    )
    records_path = summary_records_path
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
