import importlib.util
import json
import pathlib
import tempfile
import unittest

from tpw.taipei_map_assets import load_taipei_map_assets, validate_svg, _tm2

ROOT = pathlib.Path(__file__).resolve().parents[2]

class TaipeiMapAssetsTests(unittest.TestCase):
    def test_source_rebuild_and_geography(self):
        spec = importlib.util.spec_from_file_location('taipei_generator', ROOT/'tools/generate_taipei_svg.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        svg, _, transform = module.create(ROOT/'data/geography/taipei/districts.zip')
        geo, meta, published = load_taipei_map_assets(ROOT)
        self.assertEqual(svg.decode(), published)
        self.assertEqual(transform, meta['transform'])
        markets = {m['market_code']:m for m in geo['markets']}
        self.assertEqual(markets['104']['location_status'], 'verified')
        self.assertIsNotNone(markets['104']['display_x'])
        self.assertEqual(markets['109']['location_role'], 'reference_site')
        self.assertIsNone(markets['109']['display_x'])
        self.assertGreater(len(svg), 0)
        self.assertLessEqual(len(svg), 150*1024)
        # Test against unrounded original source polygon, not the display geometry.
        _, districts = module.read_source(ROOT/'data/geography/taipei/districts.zip')
        rings = next(r for d,r in districts if d['TNAME']=='中山區')
        x,y = _tm2(markets['104']['longitude'], markets['104']['latitude'])
        def inside(ring):
            odd=False
            for (x1,y1),(x2,y2) in zip(ring,ring[1:]+ring[:1]):
                if (y1>y)!=(y2>y) and x<(x2-x1)*(y-y1)/(y2-y1)+x1: odd=not odd
            return odd
        self.assertEqual(sum(inside(r) for r in rings)%2, 1)

    def test_reject_unsafe_svg(self):
        svg = (ROOT/'src/tpw/assets/taipei-districts.svg').read_text()
        for injection in ('<script/>', '<foreignObject/>', '<path onload="alert(1)"/>', '<image href="https://example.com/x"/>'):
            with self.subTest(injection=injection), self.assertRaises(ValueError):
                validate_svg(svg.replace('</svg>', injection+'</svg>'))

    def test_coordinate_swap_and_crs_rejected(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('config','data/geography/taipei','src/tpw/assets'):
                shutil.copytree(ROOT/name, pathlib.Path(tmp)/name, dirs_exist_ok=True)
            path = pathlib.Path(tmp)/'config/taipei-market-geography.json'
            geo = json.loads(path.read_text()); market=geo['markets'][0]
            market['longitude'], market['latitude'] = market['latitude'], market['longitude']
            path.write_text(json.dumps(geo))
            with self.assertRaises(ValueError): load_taipei_map_assets(tmp)
            market['longitude'], market['latitude'] = market['latitude'], market['longitude']
            market['coordinate_crs'] = 'EPSG:3826'; path.write_text(json.dumps(geo))
            with self.assertRaises(ValueError): load_taipei_map_assets(tmp)

if __name__ == '__main__': unittest.main()
