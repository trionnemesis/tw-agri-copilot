import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .model import REQUIRED

URL = "https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx"
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class UpstreamUnavailable(ValueError):
    """Transient upstream failure that may safely use last-known-good data."""


def _read_page(url, opener, timeout, attempts, backoff_seconds, sleeper):
    last_error = None
    for attempt in range(attempts):
        try:
            response = opener(url, timeout=timeout)
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            body = response.read()

            if status != 200:
                if status in RETRYABLE_STATUS:
                    raise RuntimeError(f"retryable upstream HTTP status {status}")
                raise ValueError(f"upstream HTTP status {status}")

            if not body.strip() or body.lstrip().startswith(b"<"):
                raise RuntimeError("upstream response is empty or HTML")

            if "json" not in content_type.lower():
                raise RuntimeError("upstream response content type is not JSON")

            return body
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE_STATUS:
                raise ValueError(f"upstream HTTP status {exc.code}") from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, RuntimeError) as exc:
            last_error = exc

        if attempt + 1 < attempts:
            sleeper(backoff_seconds * (2**attempt))

    raise UpstreamUnavailable(
        f"upstream unavailable after {attempts} attempts"
    ) from last_error


def fetch(
    start,
    end,
    top=1000,
    max_pages=20,
    opener=urllib.request.urlopen,
    urls=None,
    timeout=30,
    attempts=3,
    backoff_seconds=1.0,
    sleeper=time.sleep,
):
    if attempts < 1:
        raise ValueError("attempts must be positive")

    all_rows, page_hashes = [], set()
    for page in range(max_pages):
        query = urllib.parse.urlencode(
            {
                "StartDate": start,
                "EndDate": end,
                "$top": top,
                "$skip": page * top,
            }
        )
        url = URL + "?" + query
        if urls is not None:
            urls.append(url)

        body = _read_page(
            url,
            opener=opener,
            timeout=timeout,
            attempts=attempts,
            backoff_seconds=backoff_seconds,
            sleeper=sleeper,
        )

        try:
            rows = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError("upstream response is malformed JSON") from exc

        if not isinstance(rows, list):
            raise ValueError("upstream JSON must be a collection")

        if rows and any(not all(key in row for key in REQUIRED) for row in rows):
            raise ValueError("upstream row missing required fields")

        digest = hashlib.sha256(body).hexdigest()
        if rows and digest in page_hashes:
            raise ValueError("duplicate pagination page")

        page_hashes.add(digest)
        all_rows.extend(rows)
        if len(rows) < top:
            break
    else:
        raise ValueError("maximum pages reached")

    if not all_rows:
        raise UpstreamUnavailable("upstream returned no rows")

    return all_rows
