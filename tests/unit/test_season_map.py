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

    def test_duplicate_category_display_name_in_catalog_fails_closed(self):
        catalog = [
            catalog_row("香蕉", ["屏東縣"], canonical_id="banana"),
            catalog_row("香蕉", ["屏東縣"], canonical_id=None),
        ]
        with self.assertRaisesRegex(SeasonMapContractError, "duplicate"):
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

    def test_categories_axis_lists_every_registered_category_in_registry_order(self):
        payload = build_season_map_payload(
            ROOT,
            [catalog_row("香蕉", ["屏東縣"], canonical_id="banana")],
            "2026-08-27",
        )
        self.assertEqual(
            [(row["id"], row["season_semantics"], row["catalog_row_count"]) for row in payload["categories"]],
            [
                ("fruit", "official_season_registry", 1),
                ("vegetable", "official_season_registry", 0),
                ("livestock", "no_official_season_registry", 0),
                ("aquaculture", "no_official_season_registry", 0),
            ],
        )
        self.assertEqual(payload["inputs"]["seasonality_sources"], {"fruit": {"source_status": "live"}})

    def test_catalog_row_count_rejects_bool_masquerading_as_the_right_value(self):
        # fruit's catalog_row_count is 1 in this fixture, so True (== 1) would silently pass a
        # bare `isinstance(count, int)` check without the explicit bool exclusion.
        payload = build_season_map_payload(
            ROOT,
            [catalog_row("香蕉", ["屏東縣"], canonical_id="banana")],
            "2026-08-27",
        )
        tampered = copy.deepcopy(payload)
        fruit = next(row for row in tampered["categories"] if row["id"] == "fruit")
        fruit["catalog_row_count"] = True
        with self.assertRaisesRegex(SeasonMapContractError, "catalog_row_count"):
            validate_season_map_payload(tampered)

    def test_different_categories_may_use_different_source_status(self):
        payload = build_season_map_payload(
            ROOT,
            [
                catalog_row("香蕉", ["屏東縣"], canonical_id="banana", source_status="live"),
                catalog_row("胡瓜", ["屏東縣"], category="vegetable", canonical_id="cucumber", source_status="stale"),
            ],
            "2026-08-27",
        )
        self.assertEqual(
            payload["inputs"]["seasonality_sources"],
            {"fruit": {"source_status": "live"}, "vegetable": {"source_status": "stale"}},
        )

    def test_no_official_season_registry_category_in_catalog_fails_closed(self):
        for category in ("livestock", "aquaculture"):
            with self.subTest(category=category):
                with self.assertRaises(SeasonMapContractError) as ctx:
                    build_season_map_payload(
                        ROOT,
                        [catalog_row("測試品項", ["屏東縣"], category=category)],
                        "2026-08-27",
                    )
                message = str(ctx.exception)
                self.assertIn("6.2.6", message)
                self.assertIn("BC-2", message)

    def test_unregistered_category_in_catalog_fails_closed(self):
        with self.assertRaisesRegex(SeasonMapContractError, "unregistered"):
            build_season_map_payload(
                ROOT,
                [catalog_row("穀類", ["屏東縣"], category="grain")],
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

    def test_category_registry_hash_drift_fails_closed_with_config(self):
        config = load_season_map_config(ROOT)
        payload = build_season_map_payload(
            ROOT,
            [catalog_row("香蕉", ["屏東縣"], canonical_id="banana")],
            "2026-08-27",
        )
        drifted = copy.deepcopy(payload)
        drifted["inputs"]["category_registry_hash"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(SeasonMapContractError, "checked-in input hash"):
            validate_season_map_payload(drifted, config)

    def test_internal_consistency_without_config_catches_status_and_count_drift(self):
        payload = build_season_map_payload(
            ROOT,
            [catalog_row("香蕉", ["屏東縣"], canonical_id="banana")],
            "2026-08-27",
        )
        # config=None still validates internal consistency: a row whose source_status no
        # longer matches its category's declared inputs.seasonality_sources status.
        drifted_row_status = copy.deepcopy(payload)
        pingtung = next(county for county in drifted_row_status["counties"] if county["slug"] == "pingtung-county")
        pingtung["local_seasonal_produce"][0]["source_status"] = "stale"
        with self.assertRaisesRegex(SeasonMapContractError, "source status differs"):
            validate_season_map_payload(drifted_row_status)

        # A no_official_season_registry category must keep catalog_row_count at zero.
        nonzero_no_official = copy.deepcopy(payload)
        livestock = next(row for row in nonzero_no_official["categories"] if row["id"] == "livestock")
        livestock["catalog_row_count"] = 1
        with self.assertRaisesRegex(SeasonMapContractError, "zero catalog rows"):
            validate_season_map_payload(nonzero_no_official)

        # inputs.seasonality_sources must exactly match the categories that have rows: build a
        # payload with two categories present so deleting one leaves a non-empty, still-invalid dict.
        two_category_payload = build_season_map_payload(
            ROOT,
            [
                catalog_row("香蕉", ["屏東縣"], canonical_id="banana"),
                catalog_row("胡瓜", ["屏東縣"], category="vegetable", canonical_id="cucumber"),
            ],
            "2026-08-27",
        )
        missing_source = copy.deepcopy(two_category_payload)
        del missing_source["inputs"]["seasonality_sources"]["fruit"]
        with self.assertRaisesRegex(SeasonMapContractError, "seasonality sources"):
            validate_season_map_payload(missing_source)

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
            for name in ("county-registry.json", "official-produce-markets.json", "map-boundary-source.json", "produce-categories.json"):
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
