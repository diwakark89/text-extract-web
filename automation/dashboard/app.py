from __future__ import annotations

from datetime import datetime, timezone
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
    normalize_records_output_name,
    resolve_records_output_path,
)
from dashboard.file_views import (
    clean_output_directory_for_run,
    list_yaml_profiles,
    load_dashboard_settings,
    load_profile_for_url,
    load_recent_urls,
    read_checkpoint,
    read_jsonl_tail,
    resolve_latest_records_jsonl_path,
    save_dashboard_settings,
    save_profile_for_url,
    save_recent_url,
    url_host_key,
)
from dashboard.process_manager import DashboardProcessManager

OUTPUT_DIR = AUTOMATION_DIR / "output"
BASE_PROFILES_DIR = AUTOMATION_DIR / "profiles"
LEARNED_PROFILES_DIR = BASE_PROFILES_DIR / "domains"
DASHBOARD_PERSISTED_SETTING_KEYS = (
    "start_url",
    "control_resume",
    "control_headless",
    "control_prompt_for_login_at_start",
    "control_enable_auto_login",
    "control_auth_file_path",
    "control_auto_login_timeout_seconds",
    "control_humanize",
    "control_selector_debug",
    "control_require_answers",
    "control_stop_on_missing_answers",
    "control_auto_learn_profiles",
    "control_clean_output_before_run",
    "records_output_name",
    "control_max_records",
    "control_questions_per_file",
    "control_max_turns",
    "control_start_index",
    "control_min_confidence",
    "control_min_quality_score",
)


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


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _clamp_float(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


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

    persisted_settings = load_dashboard_settings(OUTPUT_DIR)

    if "start_url" not in st.session_state:
        persisted_start_url = str(persisted_settings.get("start_url") or "").strip()
        st.session_state.start_url = persisted_start_url or (recent_urls[0] if recent_urls else "")
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
    if "start_run_requested" not in st.session_state:
        st.session_state.start_run_requested = 0
    if "control_resume" not in st.session_state:
        st.session_state.control_resume = _as_bool(persisted_settings.get("control_resume"))
        if st.session_state.control_resume is None:
            st.session_state.control_resume = True
    if "control_headless" not in st.session_state:
        st.session_state.control_headless = _as_bool(persisted_settings.get("control_headless"))
        if st.session_state.control_headless is None:
            st.session_state.control_headless = False
    if "control_prompt_for_login_at_start" not in st.session_state:
        st.session_state.control_prompt_for_login_at_start = _as_bool(
            persisted_settings.get("control_prompt_for_login_at_start"),
        )
        if st.session_state.control_prompt_for_login_at_start is None:
            st.session_state.control_prompt_for_login_at_start = False
    if "control_enable_auto_login" not in st.session_state:
        st.session_state.control_enable_auto_login = _as_bool(
            persisted_settings.get("control_enable_auto_login"),
        )
        if st.session_state.control_enable_auto_login is None:
            st.session_state.control_enable_auto_login = False
    if "control_auth_file_path" not in st.session_state:
        st.session_state.control_auth_file_path = str(
            persisted_settings.get("control_auth_file_path")
            or "auth/auth_hosts.yaml",
        ).strip() or "auth/auth_hosts.yaml"
    if "control_auto_login_timeout_seconds" not in st.session_state:
        saved_auto_login_timeout = _as_int(
            persisted_settings.get("control_auto_login_timeout_seconds"),
        )
        st.session_state.control_auto_login_timeout_seconds = (
            _clamp_int(saved_auto_login_timeout, minimum=5, maximum=300)
            if saved_auto_login_timeout is not None
            else 40
        )
    if "control_humanize" not in st.session_state:
        st.session_state.control_humanize = _as_bool(persisted_settings.get("control_humanize"))
        if st.session_state.control_humanize is None:
            st.session_state.control_humanize = False
    if "control_selector_debug" not in st.session_state:
        st.session_state.control_selector_debug = _as_bool(
            persisted_settings.get("control_selector_debug"),
        )
        if st.session_state.control_selector_debug is None:
            st.session_state.control_selector_debug = False
    if "control_require_answers" not in st.session_state:
        st.session_state.control_require_answers = _as_bool(
            persisted_settings.get("control_require_answers"),
        )
        if st.session_state.control_require_answers is None:
            st.session_state.control_require_answers = True
    if "control_stop_on_missing_answers" not in st.session_state:
        st.session_state.control_stop_on_missing_answers = _as_bool(
            persisted_settings.get("control_stop_on_missing_answers"),
        )
        if st.session_state.control_stop_on_missing_answers is None:
            st.session_state.control_stop_on_missing_answers = False
    if "control_auto_learn_profiles" not in st.session_state:
        st.session_state.control_auto_learn_profiles = _as_bool(
            persisted_settings.get("control_auto_learn_profiles"),
        )
        if st.session_state.control_auto_learn_profiles is None:
            st.session_state.control_auto_learn_profiles = True
    if "control_clean_output_before_run" not in st.session_state:
        st.session_state.control_clean_output_before_run = _as_bool(
            persisted_settings.get("control_clean_output_before_run"),
        )
        if st.session_state.control_clean_output_before_run is None:
            st.session_state.control_clean_output_before_run = False
    if "records_output_name" not in st.session_state:
        st.session_state.records_output_name = normalize_records_output_name(
            str(persisted_settings.get("records_output_name") or "records.jsonl").strip()
            or "records.jsonl",
        )
    if "control_max_records" not in st.session_state:
        saved_max_records = _as_int(persisted_settings.get("control_max_records"))
        st.session_state.control_max_records = (
            _clamp_int(saved_max_records, minimum=1, maximum=5000)
            if saved_max_records is not None
            else 1000
        )
    if "control_questions_per_file" not in st.session_state:
        saved_questions_per_file = _as_int(
            persisted_settings.get("control_questions_per_file"),
        )
        st.session_state.control_questions_per_file = (
            _clamp_int(saved_questions_per_file, minimum=1, maximum=5000)
            if saved_questions_per_file is not None
            else 300
        )
    if "control_max_turns" not in st.session_state:
        saved_max_turns = _as_int(persisted_settings.get("control_max_turns"))
        st.session_state.control_max_turns = (
            _clamp_int(saved_max_turns, minimum=10, maximum=10000)
            if saved_max_turns is not None
            else 800
        )
    if "control_start_index" not in st.session_state:
        saved_start_index = _as_int(persisted_settings.get("control_start_index"))
        st.session_state.control_start_index = (
            _clamp_int(saved_start_index, minimum=1, maximum=100000)
            if saved_start_index is not None
            else 1
        )
    if "control_min_confidence" not in st.session_state:
        saved_min_confidence = _as_float(persisted_settings.get("control_min_confidence"))
        st.session_state.control_min_confidence = (
            _clamp_float(saved_min_confidence, minimum=0.0, maximum=1.0)
            if saved_min_confidence is not None
            else 0.65
        )
    if "control_min_quality_score" not in st.session_state:
        saved_min_quality_score = _as_float(
            persisted_settings.get("control_min_quality_score"),
        )
        st.session_state.control_min_quality_score = (
            _clamp_float(saved_min_quality_score, minimum=0.0, maximum=1.0)
            if saved_min_quality_score is not None
            else 0.72
        )
    if "dashboard_last_saved_settings" not in st.session_state:
        st.session_state.dashboard_last_saved_settings = {
            key: st.session_state.get(key)
            for key in DASHBOARD_PERSISTED_SETTING_KEYS
        }

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

    records_output_name = st.sidebar.text_input(
        "Records file name",
        key="records_output_name",
        help="Extension is optional. Dashboard automatically saves records as .jsonl.",
    )
    normalized_records_output_name = normalize_records_output_name(records_output_name)

    max_records = st.sidebar.number_input(
        "Max records",
        min_value=1,
        max_value=5000,
        key="control_max_records",
    )
    questions_per_file = st.sidebar.number_input(
        "Questions per file",
        min_value=1,
        max_value=5000,
        key="control_questions_per_file",
        help="Split records into numbered files after this many questions",
    )
    max_turns = st.sidebar.number_input(
        "Max turns",
        min_value=10,
        max_value=10000,
        key="control_max_turns",
    )
    resume = st.sidebar.checkbox("Resume from checkpoint", key="control_resume")
    headless = st.sidebar.checkbox("Headless", key="control_headless")
    prompt_for_login_at_start = st.sidebar.checkbox(
        "Prompt for login at start",
        key="control_prompt_for_login_at_start",
        help="Open page and wait for manual login before crawling starts.",
    )
    enable_auto_login = st.sidebar.checkbox(
        "Auto login from auth file",
        key="control_enable_auto_login",
        help="Use host-based credentials/selectors from a local auth YAML before manual prompt.",
    )
    auth_file_path = st.sidebar.text_input(
        "Auth file",
        key="control_auth_file_path",
        help="Path to local host auth YAML (kept out of git).",
    )
    auto_login_timeout_seconds = st.sidebar.number_input(
        "Auto login timeout (sec)",
        min_value=5,
        max_value=300,
        key="control_auto_login_timeout_seconds",
        step=1,
    )
    humanize = st.sidebar.checkbox(
        "Human-like crawl pacing",
        key="control_humanize",
        help="Use randomized pauses, reading delays, and natural click timing to reduce bot-like behavior.",
    )
    selector_debug = st.sidebar.checkbox("Selector debug", key="control_selector_debug")
    require_answers = st.sidebar.checkbox("Require answers", key="control_require_answers")
    stop_on_missing_answers = st.sidebar.checkbox("Stop if answers missing", key="control_stop_on_missing_answers")
    auto_learn_profiles = st.sidebar.checkbox("Auto learn profiles", key="control_auto_learn_profiles")
    clean_output_before_run = st.sidebar.checkbox(
        "Clean output folder before run",
        key="control_clean_output_before_run",
        help="Delete prior crawler output files and folders before starting this run.",
    )
    start_index = st.sidebar.number_input(
        "Start index",
        min_value=1,
        max_value=100000,
        key="control_start_index",
    )
    min_confidence = st.sidebar.number_input(
        "Min confidence",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
        key="control_min_confidence",
    )
    min_quality_score = st.sidebar.number_input(
        "Min quality score",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
        key="control_min_quality_score",
    )
    dashboard_settings = {
        "start_url": start_url.strip(),
        "control_resume": bool(resume),
        "control_headless": bool(headless),
        "control_prompt_for_login_at_start": bool(prompt_for_login_at_start),
        "control_enable_auto_login": bool(enable_auto_login),
        "control_auth_file_path": auth_file_path.strip() or "auth/auth_hosts.yaml",
        "control_auto_login_timeout_seconds": int(auto_login_timeout_seconds),
        "control_humanize": bool(humanize),
        "control_selector_debug": bool(selector_debug),
        "control_require_answers": bool(require_answers),
        "control_stop_on_missing_answers": bool(stop_on_missing_answers),
        "control_auto_learn_profiles": bool(auto_learn_profiles),
        "control_clean_output_before_run": bool(clean_output_before_run),
        "records_output_name": normalized_records_output_name,
        "control_max_records": int(max_records),
        "control_questions_per_file": int(questions_per_file),
        "control_max_turns": int(max_turns),
        "control_start_index": int(start_index),
        "control_min_confidence": float(min_confidence),
        "control_min_quality_score": float(min_quality_score),
    }
    if dashboard_settings != st.session_state.get("dashboard_last_saved_settings"):
        save_dashboard_settings(OUTPUT_DIR, dashboard_settings)
        st.session_state.dashboard_last_saved_settings = dashboard_settings

    st.html(
        """
        <script>
        (function () {
            const parentDoc = window.parent && window.parent.document;
            if (!parentDoc || parentDoc.__mcqStartRunBlurHookInstalled) {
                return;
            }
            parentDoc.__mcqStartRunBlurHookInstalled = true;
            parentDoc.addEventListener(
                "pointerdown",
                function (event) {
                    const button = event.target && event.target.closest ? event.target.closest("button") : null;
                    if (!button) {
                        return;
                    }
                    const label = (button.innerText || "").trim().toLowerCase();
                    if (label !== "start run") {
                        return;
                    }
                    const active = parentDoc.activeElement;
                    if (active && typeof active.blur === "function") {
                        active.blur();
                    }
                },
                true,
            );
        })();
        </script>
        """
    )

    run_col, stop_col, refresh_col = st.columns([1, 1, 1])

    with run_col:
        start_disabled = manager.is_running()
        if st.button("Start run", type="primary", use_container_width=True, disabled=start_disabled):
            st.session_state.start_run_requested = 4
            st.rerun()

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

    pending_start = int(st.session_state.get("start_run_requested", 0) or 0)
    if pending_start and not manager.is_running():
        if pending_start > 1:
            st.session_state.start_run_requested = pending_start - 1
            st.rerun()

        st.session_state.start_run_requested = 0

        # Number/select widgets can lag a click in rapid UI interactions.
        # Launch only after settle reruns and read committed session values.
        committed_max_turns = int(st.session_state.get("control_max_turns", max_turns))
        if not start_url.strip():
            st.error("Start URL is required.")
        else:
            profile_path = str(selected_profile.resolve()) if selected_profile is not None else None

            if clean_output_before_run:
                removed_files, removed_dirs = clean_output_directory_for_run(OUTPUT_DIR)
                st.info(
                    f"Output folder cleaned before run ({removed_files} files, {removed_dirs} folders removed)."
                )

            options = DashboardRunOptions(
                start_url=start_url.strip(),
                profile_path=profile_path,
                resume=resume,
                headless=headless,
                max_records=int(max_records),
                questions_per_file=int(questions_per_file),
                max_turns=committed_max_turns,
                start_index=int(start_index),
                min_confidence=float(min_confidence),
                min_quality_score=float(min_quality_score),
                require_answers=require_answers,
                stop_on_missing_answers=stop_on_missing_answers,
                auto_learn_profiles=auto_learn_profiles,
                selector_debug=selector_debug,
                records_output_name=normalized_records_output_name,
                prompt_for_login_at_start=prompt_for_login_at_start,
                enable_auto_login=enable_auto_login,
                auth_file_path=auth_file_path.strip() or "auth/auth_hosts.yaml",
                auto_login_timeout_seconds=int(auto_login_timeout_seconds),
                humanize=humanize,
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
                    "questions_per_file": options.questions_per_file,
                    "stop_on_missing_answers": options.stop_on_missing_answers,
                    "records_output_path": str(
                        resolve_records_output_path(AUTOMATION_DIR, options.records_output_name)
                    ),
                    "prompt_for_login_at_start": options.prompt_for_login_at_start,
                    "enable_auto_login": options.enable_auto_login,
                    "auth_file_path": options.auth_file_path,
                    "humanize": options.humanize,
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
                manager.add_local_log(f"Python executable: {command[0]}")
                st.success(message)
            else:
                st.warning(message)

            st.code(shlex.join(command), language="bash")

    status = manager.status()
    code = manager.return_code()
    st.info(f"Process status: {status} | Return code: {code}")

    checkpoint_path = OUTPUT_DIR / "checkpoint.json"
    checkpoint = read_checkpoint(checkpoint_path)

    total_extracted_questions = _as_int(checkpoint.get("records_written")) if isinstance(checkpoint, dict) else None

    summary = st.session_state.get("last_run_summary")

    recent_logs = manager.get_logs(limit=120)
    if summary:
        if status in {"completed", "failed"} and not summary.get("stopped_at"):
            summary["stopped_at"] = datetime.now(timezone.utc).isoformat()

        st.subheader("Current run summary")
        c1, c2, c3 = st.columns(3)
        c1.metric("Status", status)
        c2.metric("Started", summary.get("started_at", ""))
        c3.metric("Stopped", summary.get("stopped_at", "-") or "-")
        st.metric("Total extracted questions", str(total_extracted_questions or 0))
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
    records_path = resolve_latest_records_jsonl_path(summary_records_path)
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
