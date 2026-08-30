import argparse
import sys

from .cli import main
from .traceability_event_recovery import preserve_same_date_h44_as_stale


ZERO_MAPPED_ERROR = "traceability market events have no explicitly mapped records"


def _requested_h44_date(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--as-of", required=True)
    args, _ = parser.parse_known_args(argv)
    return args.as_of


try:
    main()
except ValueError as exc:
    if (
        len(sys.argv) > 1
        and sys.argv[1] == "fetch-traceability-events"
        and str(exc) == ZERO_MAPPED_ERROR
    ):
        preserve_same_date_h44_as_stale(_requested_h44_date(sys.argv[2:]))
    raise
