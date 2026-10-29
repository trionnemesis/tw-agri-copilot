"""Acceptance checks for market isolation and provenance eligibility."""
import copy
import json
import unittest

from tests.unit import test_taipei_map as fixtures


class TaipeiMapAcceptanceTest(unittest.TestCase):
    setUp = fixtures.MapDataTest.setUp
    row = fixtures.MapDataTest.row
    build = fixtures.MapDataTest.build

    @staticmethod
    def series(doc, code, crop='LA2'):
        return next(s for s in doc['series'] if s['market_code'] == code and s['product_code_raw'] == crop)

    @staticmethod
    def comparison(doc, crop='LA2'):
        return next(c for c in doc['comparisons'] if c['product_code_raw'] == crop)

    def test_non_taipei_extreme_has_no_effect(self):
        rows = [self.row('2026-08-25', '104', 30, 10), self.row('2026-08-25', '109', 40, 20, 'c')]
        baseline = self.build(rows)
        outsider = copy.deepcopy(rows[0])
        outsider.update(market_code='220', market_name='其他市場', avg_price_twd_per_kg=999999999, volume_kg=999999999)
        self.assertEqual(baseline, self.build(rows + [outsider]))

    def test_market_104_changes_without_changing_109_series(self):
        rows = [self.row('2026-08-25', '104', 30, 10), self.row('2026-08-25', '109', 40, 20, 'c')]
        before = self.build(rows)
        modified = copy.deepcopy(rows)
        modified[0].update(avg_price_twd_per_kg=90, volume_kg=50, row_hash='sha256:'+'d'*64)
        after = self.build(modified)
        self.assertEqual(self.series(before, '109'), self.series(after, '109'))
        self.assertNotEqual(self.series(before, '104'), self.series(after, '104'))
        self.assertEqual(self.comparison(after)['price_104'], 90)
        self.assertEqual(self.comparison(after)['price_109'], 40)

    def test_distinct_raw_codes_are_not_combined(self):
        self.items.append({'canonical_id':'carrot', 'display_name':'胡蘿蔔', 'market_crop_codes':['SB1', 'SB2']})
        one = self.row('2026-08-25', '104', 30, 10)
        one.update(canonical_id='carrot', crop_code='SB1', crop_name_raw='胡蘿蔔未洗')
        two = self.row('2026-08-25', '109', 40, 20, 'c')
        two.update(canonical_id='carrot', crop_code='SB2', crop_name_raw='胡蘿蔔清洗')
        doc = self.build([one, two])
        for crop in ('SB1', 'SB2'):
            comp = self.comparison(doc, crop)
            self.assertEqual(comp['comparison_status'], 'not_comparable')
            self.assertIsNone(comp['absolute_gap'])
            self.assertIsNone(comp['relative_gap_pct'])
        self.assertEqual(self.comparison(doc, 'SB1')['price_104'], 30)
        self.assertIsNone(self.comparison(doc, 'SB1')['price_109'])
        self.assertEqual(self.comparison(doc, 'SB2')['price_109'], 40)
        self.assertIsNone(self.comparison(doc, 'SB2')['price_104'])

    def test_row_timestamp_may_differ_from_manifest(self):
        row = self.row('2026-08-25', '104', 30, 10)
        row['fetched_at'] = '2026-08-24T12:00:00+08:00'
        doc = self.build([row])
        self.assertEqual(self.comparison(doc)['price_104'], 30)
        self.assertEqual(doc['inputs']['lineage_level'], 'normalized_snapshot_with_ingestion_metadata')
        self.assertFalse(doc['inputs']['raw_replay_available'])
        self.assertTrue(doc['inputs']['source_manifest_refs'])

    def test_different_dates_are_not_compared(self):
        rows = [self.row('2026-08-24', '104', 30, 10), self.row('2026-08-25', '109', 40, 20, 'c')]
        doc = self.build(rows)
        comp = self.comparison(doc)
        self.assertIsNone(comp['price_104'])
        self.assertEqual(comp['price_109'], 40)
        self.assertEqual(comp['date'], '2026-08-25')
        self.assertEqual(comp['comparison_status'], 'not_comparable')
        self.assertIsNone(comp['absolute_gap'])
        self.assertEqual(self.series(doc, '104')['days'][-2]['price_twd_per_kg'], 30)

    def test_zero_volume_and_negative_are_not_observed(self):
        zero = self.row('2026-08-24', '104', 30, 0)
        negative = self.row('2026-08-25', '104', -10, 20, 'c')
        doc = self.build([zero, negative])
        days = self.series(doc, '104')['days']
        self.assertEqual(days[-2]['observation_status'], 'zero_volume')
        self.assertIsNone(days[-2]['price_twd_per_kg'])
        self.assertIsNone(days[-2]['volume_kg'])
        self.assertNotEqual(days[-1]['observation_status'], 'observed')
        self.assertIsNone(days[-1]['price_twd_per_kg'])
        q = next(q for q in doc['quality']['by_date_market'] if q['date'] == '2026-08-25' and q['market_code'] == '104')
        self.assertEqual(q['invalid'], 1)
        self.assertEqual(q['reasons']['invalid_value'], 1)

    def test_bad_manifest_role_and_hash_exclude_observations(self):
        path = self.root/'data/source-meta/2026-08-25.json'
        original = json.loads(path.read_text())
        for field, value in [('source_role', 'supplemental'), ('content_hash', 'sha256:not-a-valid-hash')]:
            with self.subTest(field=field):
                manifest = dict(original, **{field:value})
                path.write_text(json.dumps(manifest))
                doc = self.build([self.row('2026-08-25', '104', 30, 10)])
                self.assertIsNone(self.comparison(doc)['price_104'])
                self.assertEqual(self.series(doc, '104')['days'][-1]['observation_status'], 'provenance_unknown')
                q = next(q for q in doc['quality']['by_date_market'] if q['date'] == '2026-08-25' and q['market_code'] == '104')
                self.assertEqual(q['provenance_unknown'], 1)
                self.assertEqual(doc['inputs']['source_manifest_refs'], [])
