#!/usr/bin/env python3
"""Manually rebuild the reviewed county SVG from the pinned official GML archive.

This tool is intentionally not part of the daily publication workflow. Boundary
updates are behavior changes and must be regenerated and reviewed in a dedicated PR.

Usage:
  python3 tools/generate_county_svg.py \
    --source /tmp/COUNTY_MOI_1140318_.zip \
    --output src/tpw/assets/taiwan-counties.svg
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import zipfile
import xml.etree.ElementTree as ET


EXPECTED_SOURCE_SHA256 = "f4589a7c65bbb905e40b1eaee332df71f4000a366f2a6f2221a64f64ef314d61"
EXPECTED_OUTPUT_SHA256 = "08e2560b4e989ec6c8730ba365776778e5261a2c36990fe94e576323775e4fbd"
EXPECTED_MEMBER = "COUNTY_MOI_1140318.gml"
INSET_BOXES = {
    "連江縣": (20, 50, 200, 170),
    "金門縣": (20, 270, 200, 170),
    "澎湖縣": (20, 500, 200, 230),
}


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _perpendicular(point, start, end):
    x, y = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    return abs(dy * x - dx * y + x2 * y1 - y2 * x1) / math.hypot(dx, dy)


def _simplify(points, tolerance):
    if len(points) <= 2:
        return points
    start, end = points[0], points[-1]
    index = -1
    maximum = 0.0
    for candidate_index, point in enumerate(points[1:-1], 1):
        distance = _perpendicular(point, start, end)
        if distance > maximum:
            index = candidate_index
            maximum = distance
    if maximum > tolerance:
        left = _simplify(points[: index + 1], tolerance)
        right = _simplify(points[index:], tolerance)
        return left[:-1] + right
    return [start, end]


def _polygon_area(points):
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
        / 2
    )


def _fit_transform(rings, box):
    points = [point for ring in rings for point in ring]
    minimum_x = min(point[0] for point in points)
    maximum_x = max(point[0] for point in points)
    minimum_y = min(point[1] for point in points)
    maximum_y = max(point[1] for point in points)
    x, y, width, height = box
    scale = min(width / (maximum_x - minimum_x), height / (maximum_y - minimum_y))
    offset_x = x + (width - (maximum_x - minimum_x) * scale) / 2
    offset_y = y + (height - (maximum_y - minimum_y) * scale) / 2
    return [
        [
            (
                offset_x + (point_x - minimum_x) * scale,
                offset_y + (maximum_y - point_y) * scale,
            )
            for point_x, point_y in ring
        ]
        for ring in rings
    ]


def _main_transform(rings):
    return [
        [
            (300 + (point_x - 119.7) * 150, 850 - (point_y - 21.65) * 200)
            for point_x, point_y in ring
        ]
        for ring in rings
    ]


def _read_registry(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    counties = payload.get("counties")
    if not isinstance(counties, list) or len(counties) != 22:
        raise ValueError("county registry must contain exactly 22 entries")
    return [
        (county["county_code"], county["slug"], county["display_name"], county["svg_path_id"])
        for county in counties
    ]


def _read_gml(source):
    raw_archive = source.read_bytes()
    if _sha256(raw_archive) != EXPECTED_SOURCE_SHA256:
        raise ValueError("source archive hash differs from the reviewed GML resource")
    features = {}
    with zipfile.ZipFile(source) as archive:
        if archive.namelist() != [EXPECTED_MEMBER]:
            raise ValueError("source archive member set differs from the reviewed resource")
        with archive.open(EXPECTED_MEMBER) as gml:
            for _, element in ET.iterparse(gml, events=("end",)):
                if not element.tag.endswith("PUB_行政區域"):
                    continue
                name = next(child.text for child in element if child.tag.endswith("名稱"))
                code = next(child.text for child in element if child.tag.endswith("行政區域代碼"))
                rings = []
                for coordinates in element.iter():
                    if not coordinates.tag.endswith("coordinates") or not coordinates.text:
                        continue
                    ring = [
                        tuple(map(float, token.split(",")[:2]))
                        for token in coordinates.text.split()
                    ]
                    if len(ring) >= 4:
                        if ring[0] == ring[-1]:
                            ring = ring[:-1]
                        rings.append(ring)
                if name in features:
                    raise ValueError("source GML contains a duplicate county")
                features[name] = (code, rings)
                element.clear()
    if len(features) != 22:
        raise ValueError("source GML must contain exactly 22 counties")
    return features


def _build_paths(registry, features):
    paths = {}
    for county_code, slug, name, _ in registry:
        if name not in features or features[name][0] != county_code:
            raise ValueError("source GML county code/name differs from the registry")
        rings = features[name][1]
        if name in INSET_BOXES:
            transformed = _fit_transform(rings, INSET_BOXES[name])
        else:
            rings = [
                ring
                for ring in rings
                if 119.7 <= sum(point[0] for point in ring) / len(ring) <= 122.25
                and 21.6 <= sum(point[1] for point in ring) / len(ring) <= 25.75
            ]
            transformed = _main_transform(rings)
        simplified = []
        for ring in transformed:
            points = _simplify(ring + [ring[0]], 0.75)
            if points[0] == points[-1]:
                points = points[:-1]
            if len(points) >= 3 and _polygon_area(points) >= 0.6:
                simplified.append((_polygon_area(points), points))
        simplified = sorted(simplified, reverse=True)[:80]
        if not simplified:
            raise ValueError("conversion retained no geometry for " + name)
        paths[slug] = " ".join(
            "M" + " ".join(f"{x:.1f},{y:.1f}" for x, y in points) + "Z"
            for _, points in simplified
        )
    return paths


def _render(registry, paths):
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 900" role="img" aria-labelledby="county-map-title" data-season-map="counties">',
        '  <title id="county-map-title">臺灣二十二縣市產季地圖</title>',
    ]
    inset_names = set(INSET_BOXES)
    regions = (
        ("main-island", [name for _, _, name, _ in registry if name not in inset_names]),
        ("penghu-inset", ["澎湖縣"]),
        ("kinmen-inset", ["金門縣"]),
        ("lienchiang-inset", ["連江縣"]),
    )
    for region, names in regions:
        lines.append(f'  <g data-region="{region}">')
        for _, slug, name, path_id in registry:
            if name not in names:
                continue
            lines.extend(
                (
                    f'    <a href="#county-{slug}" aria-label="{name}" data-county-link="{slug}">',
                    f'      <path id="{path_id}" data-county-path="{slug}" fill-rule="evenodd" d="{paths[slug]}"/>',
                    "    </a>",
                )
            )
        lines.append("  </g>")
    lines.append("</svg>")
    return ("\n".join(lines) + "\n").encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument(
        "--registry",
        default=pathlib.Path("config/county-registry.json"),
        type=pathlib.Path,
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    registry = _read_registry(args.registry)
    generated = _render(registry, _build_paths(registry, _read_gml(args.source)))
    if _sha256(generated) != EXPECTED_OUTPUT_SHA256:
        raise ValueError("generated SVG hash differs from the reviewed asset")
    if args.check:
        if not args.output.exists() or args.output.read_bytes() != generated:
            raise ValueError("checked-in SVG differs from the deterministic conversion")
        print("county SVG matches the reviewed deterministic conversion")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(generated)
    print("wrote", args.output, "sha256:" + _sha256(generated))


if __name__ == "__main__":
    main()
