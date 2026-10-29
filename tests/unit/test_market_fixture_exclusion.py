import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from tpw import cli
from tpw.season_map import load_official_market_registry
from tpw.publication import classify_market_status
from tpw.schedule import latest_complete_date
from tpw.analytics import aggregate, build_series, market_rows_for_analysis
from tpw.taipei_analysis import build_taipei_analysis
from tests.unit.test_taipei_analysis import AS_OF, ITEMS, ROOT, calendar, history, publication, row


class MarketFixtureExclusionTest(unittest.TestCase):
    def test_live_aggregate_excludes_fixture_even_with_real_source_id(self):
        real = dict(row(AS_OF, '104', 'banana', 20, 10), fetched_at=AS_OF+'T12:00:00Z')
        fake = row(AS_OF, '109', 'banana', 99999, 100000)
        self.assertEqual(aggregate([real, fake]), aggregate([real]))
        self.assertEqual(aggregate([fake]), [])
        self.assertEqual(aggregate([fake], include_fixtures=True)[0]['market_count'], 1)
        self.assertEqual(market_rows_for_analysis([dict(real, source_status=' Fixture ')]), [])
        self.assertEqual(market_rows_for_analysis([dict(real, fetched_at=' FIXTURE ')]), [])

    def test_history_cannot_inflate_coverage_ranges_or_previous_day(self):
        live = dict(row(AS_OF, '104', 'banana', 20, 10), fetched_at=AS_OF+'T12:00:00Z')
        fake_history = history()
        value = build_series(aggregate(fake_history+[live]), AS_OF)[0]
        for window in value['windows'].values():
            self.assertEqual(window['coverage_days'], 1)
            self.assertEqual(window['price_twd_per_kg'], 20)
            self.assertEqual(window['status'], 'insufficient')
        self.assertIsNone(value['previous_trading_day']['date'])
        self.assertEqual(value['range_stats']['90d']['observed_days'], 1)

    def test_taipei_filters_before_lineage_market_counts_and_statistics(self):
        live = dict(row(AS_OF, '104', 'banana', 20, 10), fetched_at=AS_OF+'T12:00:00Z')
        args = (AS_OF, publication(), ITEMS, load_official_market_registry(ROOT), calendar(), 'success')
        expected = build_taipei_analysis([live], *args)
        self.assertEqual(build_taipei_analysis(history()+[live], *args), expected)
        self.assertEqual(expected['observed_market_count'], 1)
        empty = build_taipei_analysis(history(), *args)
        self.assertEqual(empty['scope_status'], 'no_taipei_observation')
        self.assertEqual(empty['observations'], [])
        fixture = build_taipei_analysis(history(), *args[:-1], 'fixture')
        self.assertEqual(fixture['observed_market_count'], 2)

    def test_loaders_fail_closed_without_explicit_fixture_publication(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(cli, 'ROOT', pathlib.Path(temp)):
            path = cli.path_for(cli.ROOT/'data', AS_OF)
            cli.write_json(path, history(1))
            self.assertEqual(cli.stored_market_rows(), [])
            with self.assertRaisesRegex(ValueError, 'no valid mapped'):
                cli.load_date(AS_OF)
            cli.write_json(cli.ROOT/'data/source-meta'/(AS_OF+'.json'), {'status':'fixture'})
            self.assertTrue(cli.load_date(AS_OF))
            self.assertTrue(cli.stored_market_rows(include_fixtures=True))
            cli.write_json(cli.ROOT/'data/source-meta'/(AS_OF+'.json'), {'status':'success'})
            with self.assertRaises(ValueError):
                cli.load_date(AS_OF)

    def test_fixture_cannot_complete_a_live_publication(self):
        live = dict(row(AS_OF, '104', 'banana', 20, 10), fetched_at=AS_OF+'T12:00:00Z')
        fake = row(AS_OF, '109', 'cabbage', 30, 10)
        result = classify_market_status([live], [live, fake], AS_OF, {'banana','cabbage'}, 'success')
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['covered_watchlist_count'], 1)

    def test_resolver_skips_fixture_only_and_mixed_incomplete_dates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            cli.write_json(root/'config/produce.yml', {'items': ITEMS})
            for date, fake in [('2026-08-23',False), ('2026-08-24',True), (AS_OF,True)]:
                values = [row(date, '104', name, 20, 10) for name in ('banana','cabbage')]
                for value in values:
                    if not fake or (date == AS_OF and value['canonical_id']=='banana'):
                        value['fetched_at'] = date+'T12:00:00Z'
                cli.write_json(cli.path_for(root/'data', date), values)
            self.assertEqual(latest_complete_date(root, AS_OF), '2026-08-23')
