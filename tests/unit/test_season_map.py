import copy
import json
import pathlib
import shutil
import tempfile
import unittest

from tpw.season_map import (
    SeasonMapContractError,
    build_season_map_payload,
    canonical_hash,
    load_season_map_config,
    validate_boundary_svg,
    validate_season_map_payload,
)


ROOT = pathlib.Path(__file__).parents[2]


def catalog_row(
    display_name,
    counties,
    *,
    category="fruit",
    canonical_id=None,
    source_status="live",
    month="2026-08",
):
    return {
        "schema_version": "1.0",
        "month": month,
        "canonical_id": canonical_id,
        "display_name": display_name,
        "source_display_names": [display_name],
        "category": category,
        "counties": counties,
        "county_count": len(counties),
        "district_count": 0,
        "varieties": [],
        "variety_count": 0,
        "source_url": "https://www.afa.gov.tw/cht/index.php?code=list&ids=1103",
        "source_status": source_status,
        "fetched_at": "fixture",
    }


class SeasonMapTest(unittest.TestCase):
    def test_checked_in_config_and_svg_cover_exactly_22_counties(self):
        config = load_season_map_config(ROOT)
        self.assertEqual(len(config.county_registry["counties"]), 22)
        self.assertEqual(len(config.market_registry["markets"]), 2)
        self.assertLessEqual(len(config.svg), 128 * 1024)
        self.assertEqual(config.geometry_hash, config.boundary_source["geometry_hash"])
        self.assertTrue(
            all(
                county["svg_path_id"] != "county-" + county["slug"]
                for county in config.county_registry["counties"]
            )
        )
        self.assertEqual(
            {county["slug"] for county in config.county_registry["counties"]},
            {
                "taipei-city",
                "new-taipei-city",
                "keelung-city",
                "taoyuan-city",
                "hsinchu-city",
                "hsinchu-county",
                "miaoli-county",
                "taichung-city",
                "changhua-county",
                "nantou-county",
                "yunlin-county",
                "chiayi-city",
                "chiayi-county",
                "tainan-city",
                "kaohsiung-city",
                "pingtung-county",
                "yilan-county",
                "hualien-county",
                "taitung-county",
                "penghu-county",
                "kinmen-county",
                "lienchiang-county",
            },
        )

    def test_payload_uses_exact_aliases_and_reports_unknown_counties(self):
        catalog = [
            catalog_row("木瓜", ["台南市", "臺北市", "未登錄縣"], canonical_id="papaya"),
            catalog_row(
                "胡瓜",
                ["臺北市"],
                category="vegetable",
                canonical_id="cucumber",
            ),
        ]
        payload = build_season_map_payload(ROOT, catalog, "2026-08-27")
        by_slug = {county["slug"]: county for county in payload["counties"]}
        self.assertEqual(payload["unmapped_source_counties"], ["未登錄縣"])
        self.assertEqual(
            [row["display_name"] for row in by_slug["tainan-city"]["local_seasonal_produce"]],
            ["木瓜"],
        )
        self.assertEqual(
            [(row["category"], row["display_name"]) for row in by_slug["taipei-city"]["local_seasonal_produce"]],
            [("fruit", "木瓜"), ("vegetable", "胡瓜")],
        )
        self.assertEqual(by_slug["new-taipei-city"]["seasonal_catalog_count"], 0)

    def test_taipei_markets_preserve_verified_104_109_evidence(self):
        payload = build_season_map_payload(
            ROOT,
            [catalog_row("香蕉", ["屏東縣"], canonical_id="banana")],
            "2026-08-27",
        )
        taipei = next(county for county in payload["counties"] if county["slug"] == "taipei-city")
        self.assertEqual(
            [(market["market_code"], market["feed_market_name"], market["official_name"]) for market in taipei["official_markets"]],
            [
                ("104", "臺北二", "第二果菜批發市場"),
                ("109", "臺北一", "第一果菜批發市場"),
            ],
        )
        self.assertTrue(all(market["official_url"].startswith("https://www.tapmc.com.tw/") for market in taipei["official_markets"]))
        self.assertTrue(all(market["evidence_url"] == "https://www.tapmc.com.tw/Pages/ContactUs" for market in taipei["official_markets"]))

    def test_payload_is_deterministic_for_the_same_inputs(self):
        catalog = json.loads((ROOT / "data/seasonality/catalog/2026-08.json").read_text())
        first = build_season_map_payload(ROOT, catalog, "2026-08-27")
        second = build_season_map_payload(ROOT, catalog, "2026-08-27")
        self.assertEqual(first, second)
        self.assertEqual(first["inputs"]["seasonality_snapshot_hash"], canonical_hash(catalog))
        self.assertEqual(canonical_hash(first), canonical_hash(second))

    def test_duplicate_county_produce_conflict_fails_closed(self):
        catalog = [
            catalog_row("香蕉", ["屏東縣"], canonical_id="banana"),
            catalog_row("香蕉", ["屏東縣"], canonical_id=None),
        ]
        with self.assertRaisesRegex(SeasonMapContractError, "conflicting catalog evidence"):
            build_season_map_payload(ROOT, catalog, "2026-08-27")

    def test_mixed_month_or_source_status_fails_closed(self):
        with self.assertRaisesRegex(SeasonMapContractError, "exactly one month"):
            build_season_map_payload(
                ROOT,
                [
                    catalog_row("香蕉", ["屏東縣"]),
                    catalog_row("鳳梨", ["屏東縣"], month="2026-09"),
                ],
                "2026-08-27",
            )
        with self.assertRaisesRegex(SeasonMapContractError, "one source status"):
            build_season_map_payload(
                ROOT,
                [
                    catalog_row("香蕉", ["屏東縣"]),
                    catalog_row("鳳梨", ["屏東縣"], source_status="stale"),
                ],
                "2026-08-27",
            )

    def test_payload_validator_rejects_count_and_registry_drift(self):
        config = load_season_map_config(ROOT)
        payload = build_season_map_payload(
            ROOT,
            [catalog_row("香蕉", ["屏東縣"], canonical_id="banana")],
            "2026-08-27",
        )
        bad_count = copy.deepcopy(payload)
        pingtung = next(county for county in bad_count["counties"] if county["slug"] == "pingtung-county")
        pingtung["seasonal_catalog_count"] = 0
        with self.assertRaisesRegex(SeasonMapContractError, "count does not match"):
            validate_season_map_payload(bad_count, config)
        bad_registry = copy.deepcopy(payload)
        bad_registry["counties"][0]["display_name"] = "猜測縣市"
        with self.assertRaisesRegex(SeasonMapContractError, "checked-in registry"):
            validate_season_map_payload(bad_registry, config)

    def test_svg_validator_rejects_active_content_and_path_drift(self):
        config = load_season_map_config(ROOT)
        active = config.svg.replace(
            b'data-county-path="taipei-city"',
            b'onclick="alert(1)"',
            1,
        )
        with self.assertRaisesRegex(SeasonMapContractError, "prohibited attribute"):
            validate_boundary_svg(active, config.county_registry)
        external = config.svg.replace(
            b'href="#county-taipei-city"',
            b'href="https://example.invalid/map"',
            1,
        )
        with self.assertRaisesRegex(SeasonMapContractError, "external attribute"):
            validate_boundary_svg(external, config.county_registry)
        missing = config.svg.replace(b'id="county-shape-taipei-city"', b'id="county-shape-taipei-city-missing"', 1)
        with self.assertRaisesRegex(SeasonMapContractError, "anchor or path contract"):
            validate_boundary_svg(missing, config.county_registry)

    def test_config_loader_rejects_duplicate_alias_and_unallowlisted_market_url(self):
        with tempfile.TemporaryDirectory() as raw:
            isolated = pathlib.Path(raw)
            (isolated / "config").mkdir()
            (isolated / "src/tpw/assets").mkdir(parents=True)
            for name in ("county-registry.json", "official-produce-markets.json", "map-boundary-source.json"):
                shutil.copy2(ROOT / "config" / name, isolated / "config" / name)
            shutil.copy2(
                ROOT / "src/tpw/assets/taiwan-counties.svg",
                isolated / "src/tpw/assets/taiwan-counties.svg",
            )
            county_path = isolated / "config/county-registry.json"
            counties = json.loads(county_path.read_text())
            counties["counties"][1]["source_names"].append("臺北市")
            county_path.write_text(json.dumps(counties, ensure_ascii=False))
            with self.assertRaisesRegex(SeasonMapContractError, "multiple counties"):
                load_season_map_config(isolated)
            shutil.copy2(ROOT / "config/county-registry.json", county_path)
            market_path = isolated / "config/official-produce-markets.json"
            markets = json.loads(market_path.read_text())
            markets["markets"][0]["official_url"] = "https://example.invalid/"
            market_path.write_text(json.dumps(markets, ensure_ascii=False))
            with self.assertRaisesRegex(SeasonMapContractError, "allowlisted HTTPS"):
                load_season_map_config(isolated)


if __name__ == "__main__":
    unittest.main()
