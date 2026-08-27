import datetime as dt
import hashlib
import json
import pathlib
import re


RUN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
INPUT_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
TRIGGERS = {"schedule", "manual", "agent-request"}
OPERATIONS = {"upsert-data", "add-analysis", "refresh-fields"}
STATUSES = {"proposed"}
REQUIRED = {
    "schema_version",
    "run_id",
    "trigger",
    "requested_at",
    "as_of_date",
    "operation",
    "source_refs",
    "model",
    "prompt_version",
    "input_hash",
    "fields_changed",
    "analysis",
    "assumptions",
    "status",
}


def canonical_input_hash(value):
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def validate_agent_run(run):
    if not isinstance(run, dict):
        raise ValueError("agent run must be a JSON object")
    missing = sorted(REQUIRED - run.keys())
    unknown = sorted(run.keys() - REQUIRED)
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))
    if unknown:
        raise ValueError("unknown fields: " + ", ".join(unknown))
    if run["schema_version"] != "1.0":
        raise ValueError("schema_version must be 1.0")
    if not isinstance(run["run_id"], str) or not RUN_ID.fullmatch(run["run_id"]):
        raise ValueError("invalid run_id")
    if run["trigger"] not in TRIGGERS:
        raise ValueError("invalid trigger")
    if run["operation"] not in OPERATIONS:
        raise ValueError("invalid operation")
    if run["status"] not in STATUSES:
        raise ValueError("invalid status")
    if not isinstance(run["input_hash"], str) or not INPUT_HASH.fullmatch(
        run["input_hash"]
    ):
        raise ValueError("invalid input_hash")
    try:
        requested = dt.datetime.fromisoformat(run["requested_at"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("requested_at must be ISO-8601") from exc
    if requested.tzinfo is None:
        raise ValueError("requested_at must include a timezone")
    try:
        dt.date.fromisoformat(run["as_of_date"])
    except (TypeError, ValueError) as exc:
        raise ValueError("as_of_date must be YYYY-MM-DD") from exc
    for field in ("source_refs", "fields_changed", "assumptions"):
        if not isinstance(run[field], list) or not all(
            isinstance(item, str) for item in run[field]
        ):
            raise ValueError(field + " must be an array of strings")
    for field in ("model", "prompt_version"):
        if not isinstance(run[field], str) or not run[field]:
            raise ValueError(field + " must be a non-empty string")
    if not isinstance(run["analysis"], dict):
        raise ValueError("analysis must be an object")
    return run


def validate_agent_run_file(path):
    path = pathlib.Path(path)
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid agent run file {path}: {exc}") from exc
    validate_agent_run(run)
    if path.parent.name == "agent-runs" and path.name != run["run_id"] + ".json":
        raise ValueError("agent run filename must match run_id")
    return run
