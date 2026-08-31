import argparse
import datetime as dt
import sys

from . import cli
from .traceability_event_recovery import preserve_same_date_h44_as_stale
from .trend_quant import enhance_price_trends


ZERO_MAPPED_ERROR = "traceability market events have no explicitly mapped records"
H44_COMMAND = "fetch-traceability-events"


def _normalize_h44_argv(argv, today=None):
    argv = list(argv)
    if not argv or argv[0] != H44_COMMAND:
        return argv, None

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("cmd")
    parser.add_argument("--as-of")
    args, _ = parser.parse_known_args(argv)
    requested_date = args.as_of or (today or dt.date.today()).isoformat()
    if args.as_of is None:
        argv.extend(["--as-of", requested_date])
    return argv, requested_date


def main(argv=None):
    source_argv = sys.argv[1:] if argv is None else argv
    normalized_argv, requested_h44_date = _normalize_h44_argv(source_argv)
    try:
        result = cli.main(normalized_argv)
        if normalized_argv and normalized_argv[0] == "build":
            enhance_price_trends()
        return result
    except ValueError as exc:
        if requested_h44_date is not None and str(exc) == ZERO_MAPPED_ERROR:
            preserve_same_date_h44_as_stale(requested_h44_date)
        raise
