"""Independent, provenance-gated market/raw-crop Taipei map projection.

Ingestion metadata supports snapshot lineage, not proof that individual rows occur in raw bytes.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import math
import re
from pathlib import Path

from .analytics import WINDOWS
from .taipei_analysis import SOURCE_ID, SOURCE_URL, feed_market_name_key, taipei_markets

SEMANTICS = 'wholesale_market_daily_transaction'
ROLE = 'authoritative_final'
HASH = re.compile(r'^sha256:[0-9a-f]{64}$')
DEFAULT = {'item': 'cabbage', 'crop': 'LA2', 'market': 'all', 'window': '30d'}

class TaipeiMapError(ValueError):
    pass

def _hash(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def _file_hash(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()

def _date(value):
    if not isinstance(value, str) or dt.date.fromisoformat(value).isoformat() != value:
        raise TaipeiMapError('invalid ISO date')
    return value

def _timestamp(value):
    try:
        return isinstance(value, str) and dt.datetime.fromisoformat(value.replace('Z', '+00:00')).utcoffset() is not None
    except (ValueError, TypeError):
        return False

def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def _policy(mode):
    if mode not in ('observed', 'fixture'):
        raise TaipeiMapError('invalid map mode')
    return {'analysis_input_policy': 'taipei-map-' + mode + '-v1', 'method_version': '1.0',
            'price_unit': 'TWD/kg', 'volume_unit': 'kg', 'window_definition': 'inclusive calendar days ending as_of_date',
            'minimum_days': {key: minimum for key, (_, minimum) in WINDOWS.items()},
            'comparison_definition': '104 minus 109; relative 104/109 - 1', 'default_selection': DEFAULT.copy()}

def _header(as_of_date, publication_status, mode):
    _date(as_of_date); _date(publication_status['requested_date'])
    if as_of_date > publication_status['requested_date'] or publication_status.get('resolved_date') != as_of_date:
        raise TaipeiMapError('publication dates do not match')
    return {'schema_version': '1.0', 'scope_id': 'taipei-city', 'market_level': 'wholesale', 'data_mode': mode,
            'requested_date': publication_status['requested_date'], 'as_of_date': as_of_date,
            'publication_status': publication_status['status'], 'policy': _policy(mode)}

def failed_taipei_map(as_of_date, publication_status, reason, mode='observed'):
    doc = {**_header(as_of_date, publication_status, mode), 'analysis_status': 'failed', 'failure_reason': str(reason),
           'inputs': None, 'geography': None, 'items': [], 'series': [], 'statistics': [], 'comparisons': [],
           'quality': None}
    return validate_taipei_map(doc, mode)

def _manifests(root, mode):
    out = []
    for path in sorted((Path(root) / 'data/source-meta').glob('*.json')):
        try:
            obj = json.loads(path.read_text(encoding='utf-8'))
            start, end = _date(obj['requested_start']), _date(obj['requested_end'])
            fixture = mode == 'fixture'
            valid = (start <= end and obj.get('source_id') == SOURCE_ID and obj.get('source_url') == SOURCE_URL
                     and obj.get('status') == ('fixture' if fixture else 'success')
                     and isinstance(obj.get('http_status'), int) and not isinstance(obj['http_status'], bool)
                     and 200 <= obj['http_status'] < 300 and bool(HASH.fullmatch(obj.get('content_hash', '')))
                     and (obj.get('retrieved_at', obj.get('fetched_at')) == 'fixture' if fixture else _timestamp(obj.get('retrieved_at')))
                     and (obj.get('source_role', ROLE) == ROLE if fixture else obj.get('source_role') == ROLE)
                     and (obj.get('dataset_semantics', SEMANTICS) == SEMANTICS if fixture else obj.get('dataset_semantics') == SEMANTICS))
            if valid:
                out.append({'path': path.relative_to(root).as_posix(), 'hash': _file_hash(path), 'start': start, 'end': end})
        except (ValueError, TypeError, KeyError, OSError):
            continue
    from .source_adapter import validate_source_run_document
    for path in sorted((Path(root) / 'data/source-runs').glob('*.json')):
        try:
            obj = validate_source_run_document(json.loads(path.read_text(encoding='utf-8')))
            start, end = _date(obj['requested_start']), _date(obj['requested_end'])
            for run in obj['runs']:
                fixture = mode == 'fixture'
                if (run.get('source_id') == SOURCE_ID and run.get('source_url') == SOURCE_URL
                    and run.get('source_role') == ROLE and run.get('dataset_semantics') == SEMANTICS
                    and run.get('status') == ('fixture' if fixture else 'success')
                    and isinstance(run.get('http_status'), int) and not isinstance(run['http_status'], bool) and 200 <= run['http_status'] < 300
                    and bool(HASH.fullmatch(str(run.get('content_hash', ''))))
                    and (run.get('retrieved_at') == 'fixture' if fixture else _timestamp(run.get('retrieved_at')))):
                    out.append({'path': path.relative_to(root).as_posix(), 'hash': _file_hash(path), 'start': start, 'end': end})
                    break
        except (ValueError, TypeError, KeyError, OSError):
            continue
    return out

def _fixture(row):
    return row.get('fetched_at') == 'fixture' or row.get('source_status') == 'fixture' or row.get('data_mode') == 'fixture' or row.get('is_fixture') is True

def _dates(start, end):
    day = dt.date.fromisoformat(start); end = dt.date.fromisoformat(end)
    while day <= end:
        yield day.isoformat(); day += dt.timedelta(days=1)

def _schedule(calendar_for, date, code):
    calendar = calendar_for(date)
    market = next((x for x in calendar.get('markets', []) if str(x.get('market_code')) == code), None)
    return market.get('schedule_status', 'unknown') if market else 'unknown'

def _stats(days, as_of):
    windows = {}
    for name, (length, minimum) in WINDOWS.items():
        selected = [d for d in days[-length:] if d['observation_status'] == 'observed']
        volume = sum(d['volume_kg'] for d in selected)
        count = len(selected)
        windows[name] = {'price_twd_per_kg': round(sum(d['price_twd_per_kg'] * d['volume_kg'] for d in selected) / volume, 6) if volume else None,
                         'total_volume_kg': round(volume, 6) if count else None, 'coverage_days': count, 'minimum_days': minimum,
                         'status': 'valid' if count >= minimum else 'insufficient',
                         'insufficient_reason': None if count >= minimum else 'coverage_below_minimum'}
    valid = [d for d in days if d['observation_status'] == 'observed']
    latest = valid[-1] if valid else None
    previous = valid[-2] if len(valid) >= 2 else None
    return windows, {'date': previous['date'] if previous else None,
                     'price_twd_per_kg': previous['price_twd_per_kg'] if previous else None,
                     'latest_date': latest['date'] if latest else None,
                     'interval_days': (dt.date.fromisoformat(latest['date']) - dt.date.fromisoformat(previous['date'])).days if previous else None,
                     'change_pct': round((latest['price_twd_per_kg'] / previous['price_twd_per_kg'] - 1) * 100, 6) if previous else None}

def build_taipei_map(rows, as_of_date, publication_status, items, market_registry, calendar_for, root, geography, geometry, mode='observed'):
    header = _header(as_of_date, publication_status, mode)
    markets = taipei_markets(market_registry)
    by_market = {str(m['market_code']): m for m in markets}
    if set(by_market) != {'104', '109'}:
        raise TaipeiMapError('Taipei map requires exactly markets 104 and 109')
    mapping = {}
    for item in items:
        for crop in item['market_crop_codes']:
            if crop in mapping: raise TaipeiMapError('crop has multiple canonical items')
            mapping[crop] = item
    if 'LA2' not in mapping or mapping['LA2']['canonical_id'] != 'cabbage': raise TaipeiMapError('default crop is not configured')
    manifests = _manifests(root, mode)
    start = (dt.date.fromisoformat(as_of_date) - dt.timedelta(days=89)).isoformat()
    eligible, quality_rows, used = {}, {}, set()
    for row in rows:
        code = str(row.get('market_code', '')); crop = row.get('crop_code')
        if code not in by_market or row.get('source_id') != SOURCE_ID or crop not in mapping: continue
        date = row.get('transaction_date')
        try: _date(date)
        except (ValueError, TypeError): continue
        if not start <= date <= as_of_date: continue
        key = (date, code); q = quality_rows.setdefault(key, {'observed': 0, 'fixture': 0, 'provenance_unknown': 0, 'invalid': 0, 'reasons': {}})
        reason = None
        if _fixture(row) != (mode == 'fixture'):
            reason = 'fixture' if _fixture(row) else 'provenance_unknown'
        elif feed_market_name_key(row.get('market_name', '')) != feed_market_name_key(by_market[code]['feed_market_name']):
            reason = 'invalid_market_identity'
        elif row.get('canonical_id') != mapping[crop]['canonical_id'] or not isinstance(row.get('crop_name_raw'), str) or not row['crop_name_raw'] or not HASH.fullmatch(str(row.get('row_hash', ''))):
            reason = 'invalid_row'
        elif not _number(row.get('avg_price_twd_per_kg')) or not _number(row.get('volume_kg')) or row['avg_price_twd_per_kg'] < 0 or row['volume_kg'] < 0:
            reason = 'invalid_value'
        elif (not _fixture(row) and not _timestamp(row.get('fetched_at'))) or row.get('source_role', ROLE) != ROLE or row.get('dataset_semantics', SEMANTICS) != SEMANTICS:
            reason = 'provenance_unknown'
        else:
            matching = [m for m in manifests if m['start'] <= date <= m['end']]
            if not matching: reason = 'provenance_unknown'
        if reason:
            bucket = reason if reason in ('fixture', 'provenance_unknown') else 'invalid'
            q[bucket] += 1; q['reasons'][reason] = q['reasons'].get(reason, 0) + 1
            continue
        rowkey = (date, code, crop, SEMANTICS)
        if rowkey in eligible:
            previous = eligible[rowkey]
            if previous['row_hash'] != row['row_hash'] or {k:v for k,v in previous.items() if k not in ('fetched_at','source_role','dataset_semantics','source_precedence')} != {k:v for k,v in row.items() if k not in ('fetched_at','source_role','dataset_semantics','source_precedence')}: raise TaipeiMapError('unresolved duplicate normalized observation')
            # Identical content hashes represent one observation. Choose a stable representative.
            if json.dumps(row, sort_keys=True, ensure_ascii=False) < json.dumps(previous, sort_keys=True, ensure_ascii=False): eligible[rowkey] = row
            continue
        eligible[rowkey] = row
        if row.get('avg_price_twd_per_kg') <= 0 or row.get('volume_kg') <= 0:
            q['invalid'] += 1
            r = 'zero_price' if row['avg_price_twd_per_kg'] <= 0 else 'zero_volume'
            q['reasons'][r] = q['reasons'].get(r, 0) + 1
        else:
            q['observed'] += 1
        chosen = matching[0]; used.add(chosen['path'])
        if 'source_role' not in row or 'dataset_semantics' not in row:
            q['reasons']['legacy_provenance_applied'] = q['reasons'].get('legacy_provenance_applied', 0) + 1
    ordered = [eligible[k] for k in sorted(eligible)]
    names = {}
    for r in ordered: names.setdefault(r['crop_code'], set()).add(r['crop_name_raw'])
    item_docs = [{'canonical_id': item['canonical_id'], 'display_name': item['display_name'],
                  'crops': [{'product_code_raw': c, 'product_name_raw': sorted(names.get(c, {c}))[0]} for c in sorted(item['market_crop_codes'])]}
                 for item in sorted(items, key=lambda x: x['canonical_id'])]
    series, statistics, comparisons = [], [], []
    schedules = {(date, code): _schedule(calendar_for, date, code) for date in _dates(start, as_of_date) for code in sorted(by_market)}
    for item in item_docs:
        for product in item['crops']:
            crop = product['product_code_raw']; pair = {}
            for code in sorted(by_market):
                days = []
                for date in _dates(start, as_of_date):
                    row = eligible.get((date, code, crop, SEMANTICS)); cal = schedules[date, code]
                    valid = row is not None and row['avg_price_twd_per_kg'] > 0 and row['volume_kg'] > 0
                    if valid: status = 'observed'
                    elif row is not None: status = 'zero_price' if row['avg_price_twd_per_kg'] <= 0 else 'zero_volume'
                    elif quality_rows.get((date, code), {}).get('provenance_unknown', 0): status = 'provenance_unknown'
                    elif not any(m['start'] <= date <= m['end'] for m in manifests): status = 'source_unavailable'
                    else: status = 'missing'
                    days.append({'date': date, 'price_twd_per_kg': row['avg_price_twd_per_kg'] if valid else None,
                                 'volume_kg': row['volume_kg'] if valid else None, 'observation_status': status,
                                 'calendar_status': cal, 'calendar_conflict': bool(valid and cal == 'scheduled_closed'),
                                 'row_hash': row['row_hash'] if row else None})
                series.append({'market_code': code, 'canonical_id': item['canonical_id'], **product, 'days': days})
                windows, previous = _stats(days, as_of_date)
                statistics.append({'market_code': code, 'canonical_id': item['canonical_id'], 'product_code_raw': crop, 'windows': windows, 'previous_observation': previous})
                pair[code] = days[-1]
            a, b = pair['104'], pair['109']; comparable = a['observation_status'] == b['observation_status'] == 'observed'
            comparisons.append({'canonical_id': item['canonical_id'], 'product_code_raw': crop, 'date': as_of_date,
                                'price_104': a['price_twd_per_kg'], 'price_109': b['price_twd_per_kg'],
                                'volume_104': a['volume_kg'], 'volume_109': b['volume_kg'],
                                'absolute_gap': round(a['price_twd_per_kg'] - b['price_twd_per_kg'], 6) if comparable else None,
                                'relative_gap_pct': round((a['price_twd_per_kg'] / b['price_twd_per_kg'] - 1) * 100, 6) if comparable else None,
                                'comparison_status': 'comparable' if comparable else 'not_comparable'})
    refs = [m for m in manifests if m['path'] in used]
    root = Path(root)
    input_files = []
    for date in _dates(start, as_of_date):
        path = root / 'data/market/daily' / date[:4] / date[5:7] / (date + '.json')
        if path.is_file(): input_files.append({'path': path.relative_to(root).as_posix(), 'hash': _file_hash(path)})
    for name in ('config/produce.yml', 'config/official-produce-markets.json', 'config/market-calendar.json', 'config/taipei-market-geography.json', 'config/taipei-boundary-source.json', 'data/geography/taipei/districts.zip', 'data/geography/taipei/markets.csv', 'src/tpw/assets/taipei-districts.svg'):
        path = root / name
        if path.is_file(): input_files.append({'path': name, 'hash': _file_hash(path)})
    doc = {**header, 'analysis_status': 'published', 'failure_reason': None,
           'inputs': {'normalized_input_hash': _hash(ordered), 'input_files': input_files, 'source_manifest_refs': refs,
                      'lineage_level': 'normalized_snapshot_with_ingestion_metadata', 'raw_replay_available': False},
           'geography': {'markets': geography['markets'], 'boundary': geometry}, 'items': item_docs, 'series': series, 'statistics': statistics,
           'comparisons': comparisons, 'quality': {'by_date_market': [{'date': d, 'market_code': c, **quality_rows.get((d,c), {'observed': 0, 'fixture': 0, 'provenance_unknown': 0, 'invalid': 0, 'reasons': {}})} for d in _dates(start, as_of_date) for c in sorted(by_market)],
           'calendar_conflicts': sum(x['calendar_conflict'] for s in series for x in s['days']),
           'unplaced_markets': sorted(m['market_code'] for m in geography['markets'] if m['location_status'] != 'verified' or m['display_x'] is None or m['display_y'] is None),
           'valid_days_by_market': {code: len({r['transaction_date'] for r in ordered if r['market_code'] == code and r['avg_price_twd_per_kg'] > 0 and r['volume_kg'] > 0}) for code in sorted(by_market)},
           'observed_market_count': len({r['market_code'] for r in ordered if r['transaction_date'] == as_of_date and r['avg_price_twd_per_kg'] > 0 and r['volume_kg'] > 0}),
           'observed_crop_count': len({r['crop_code'] for r in ordered if r['transaction_date'] == as_of_date and r['avg_price_twd_per_kg'] > 0 and r['volume_kg'] > 0})}}
    return validate_taipei_map(doc, mode)

def validate_taipei_map(document, expected_mode=None):
    def require(ok, message):
        if not ok: raise TaipeiMapError(message)
    def fields(obj, expected):
        require(isinstance(obj, dict) and set(obj) == set(expected.split()), 'map fields mismatch: ' + expected)
    fields(document, 'schema_version scope_id market_level data_mode requested_date as_of_date publication_status analysis_status failure_reason policy inputs geography items series statistics comparisons quality')
    mode = document['data_mode']
    require(mode in ('observed', 'fixture') and (expected_mode is None or mode == expected_mode), 'unexpected map mode')
    require(document['policy'] == _policy(mode), 'invalid policy')
    require((document['schema_version'], document['scope_id'], document['market_level']) == ('1.0', 'taipei-city', 'wholesale'), 'invalid identity')
    _date(document['as_of_date']); _date(document['requested_date'])
    require(document['as_of_date'] <= document['requested_date'], 'invalid date order')
    from .publication import MARKET_STATES
    require(document['publication_status'] in MARKET_STATES, 'invalid publication status')
    if document['analysis_status'] == 'failed':
        require(isinstance(document['failure_reason'], str) and bool(document['failure_reason'].strip()), 'failure reason required')
        require(all(document[k] == [] for k in ('items','series','statistics','comparisons')) and all(document[k] is None for k in ('inputs','geography','quality')), 'failed map must be empty')
        return document
    require(document['analysis_status'] == 'published' and document['failure_reason'] is None, 'invalid analysis status')
    inputs = document['inputs']; fields(inputs, 'normalized_input_hash input_files source_manifest_refs lineage_level raw_replay_available')
    require(bool(HASH.fullmatch(str(inputs['normalized_input_hash']))) and inputs['lineage_level'] == 'normalized_snapshot_with_ingestion_metadata' and inputs['raw_replay_available'] is False, 'invalid lineage')
    for ref in inputs['input_files']:
        fields(ref, 'path hash'); require(isinstance(ref['path'], str) and not ref['path'].startswith('/') and '..' not in Path(ref['path']).parts and bool(HASH.fullmatch(str(ref['hash']))), 'invalid input ref')
    for ref in inputs['source_manifest_refs']:
        fields(ref, 'path hash start end'); _date(ref['start']); _date(ref['end']); require(ref['start'] <= ref['end'] and ref['path'].startswith(('data/source-meta/', 'data/source-runs/')) and bool(HASH.fullmatch(str(ref['hash']))), 'invalid manifest ref')
    fields(document['geography'], 'markets boundary')
    geo = document['geography']; boundary = geo['boundary']
    fields(boundary, 'schema_version dataset_url resource_url downloaded_at source_path source_sha256 source_crs_wkt source_crs output_crs transform simplification generator output_path output_sha256 license license_url attribution')
    require(boundary['source_crs'] == boundary['output_crs'] == 'EPSG:3826' and isinstance(boundary['source_crs_wkt'], str) and 'Central_Meridian",121.0' in boundary['source_crs_wkt'], 'invalid boundary CRS')
    require(all(re.fullmatch(r'[0-9a-f]{64}',str(boundary[k])) for k in ('source_sha256','output_sha256')), 'invalid boundary hash')
    transform = boundary['transform']; fields(transform, 'min_x max_y scale offset_x offset_y view_box')
    require(all(_number(transform[k]) for k in ('min_x','max_y','scale','offset_x','offset_y')) and transform['scale'] > 0 and transform['view_box'] == [0,0,800,800], 'invalid display transform')
    require(isinstance(geo['markets'],list) and len(geo['markets']) == 2 and {m.get('market_code') for m in geo['markets']} == {'104','109'}, 'invalid market geography')
    for m in geo['markets']:
        fields(m, 'market_namespace coordinate_crs valid_from valid_to valid_time_precision verified_at address_evidence_url coordinate_evidence_url source_snapshot_hash market_code official_name district_code district_name reference_address operating_address longitude latitude location_role location_status location_note display_x display_y')
        require(all(isinstance(m[k],str) and m[k] for k in ('official_name','district_code','district_name','reference_address','location_note')), 'invalid geography text')
        require(all(m[k] is None or isinstance(m[k],str) for k in ('operating_address','address_evidence_url','coordinate_evidence_url','source_snapshot_hash')), 'invalid geography evidence')
        require(m['market_namespace'] == SOURCE_ID and m['coordinate_crs'] == 'EPSG:4326' and m['location_role'] in ('operating_site','reference_site') and m['location_status'] in ('verified','conflicting_sources','unverified'), 'invalid geography status')
        for k in ('valid_from','valid_to','verified_at'):
            if m[k] is not None: _date(m[k])
        require(not m['valid_from'] or not m['valid_to'] or m['valid_from'] <= m['valid_to'], 'invalid geography date range')
        require(m['valid_time_precision'] in ('unknown','day','month','year'), 'invalid time precision')
        require((m['longitude'] is None and m['latitude'] is None) or (_number(m['longitude']) and 121.4 < m['longitude'] < 121.7 and _number(m['latitude']) and 24.9 < m['latitude'] < 25.3), 'invalid geography coordinate')
        if m['location_status'] == 'verified':
            from .taipei_map_assets import _tm2
            require(m['location_role'] == 'operating_site' and m['longitude'] is not None and bool(m['operating_address']), 'verified operating address required')
            x,y = _tm2(m['longitude'],m['latitude']); t = transform
            require(m['display_x'] == round(t['offset_x']+(x-t['min_x'])*t['scale'],2) and m['display_y'] == round(t['offset_y']+(t['max_y']-y)*t['scale'],2), 'invalid market display transform')
        else: require(m['display_x'] is None and m['display_y'] is None, 'unverified market must not be placed')
    items = document['items']; require(isinstance(items, list) and items, 'items required')
    products = {}
    for item in items:
        fields(item, 'canonical_id display_name crops'); require(isinstance(item['canonical_id'], str) and item['canonical_id'] and isinstance(item['display_name'], str) and item['display_name'], 'invalid item')
        for product in item['crops']:
            fields(product, 'product_code_raw product_name_raw'); crop = product['product_code_raw']; require(isinstance(crop, str) and crop and isinstance(product['product_name_raw'], str) and product['product_name_raw'] and crop not in products, 'invalid crop')
            products[crop] = item['canonical_id']
    require(products.get('LA2') == 'cabbage', 'default missing')
    asof = document['as_of_date']; start = (dt.date.fromisoformat(asof)-dt.timedelta(days=89)).isoformat(); dates = list(_dates(start, asof)); index = {}
    for series in document['series']:
        fields(series, 'market_code canonical_id product_code_raw product_name_raw days')
        code, crop = series['market_code'], series['product_code_raw']; key = (code,crop)
        require(code in ('104','109') and products.get(crop) == series['canonical_id'] and key not in index, 'invalid series identity')
        days = series['days']; require(isinstance(days,list) and [d.get('date') for d in days] == dates, 'invalid date grid')
        for day in days:
            fields(day, 'date price_twd_per_kg volume_kg observation_status calendar_status calendar_conflict row_hash')
            status = day['observation_status']; require(status in ('observed','zero_price','zero_volume','provenance_unknown','source_unavailable','missing'), 'invalid observation status')
            require(day['calendar_status'] in ('expected_open','exceptional_open','scheduled_closed','unknown'), 'invalid calendar status')
            require(day['calendar_conflict'] is (status == 'observed' and day['calendar_status'] == 'scheduled_closed'), 'invalid calendar conflict')
            if status == 'observed':
                require(_number(day['price_twd_per_kg']) and day['price_twd_per_kg'] > 0 and _number(day['volume_kg']) and day['volume_kg'] > 0 and bool(HASH.fullmatch(str(day['row_hash']))), 'invalid observed values')
            else:
                require(day['price_twd_per_kg'] is None and day['volume_kg'] is None, 'missing observation has values')
                require((bool(HASH.fullmatch(str(day['row_hash']))) if status in ('zero_price','zero_volume') else day['row_hash'] is None), 'invalid missing row hash')
        index[key] = series
    require(set(index) == {(code,crop) for crop in products for code in ('104','109')}, 'missing series')
    stats_index = {}
    for stat in document['statistics']:
        fields(stat, 'market_code canonical_id product_code_raw windows previous_observation'); key = (stat['market_code'], stat['product_code_raw'])
        require(key in index and key not in stats_index and stat['canonical_id'] == index[key]['canonical_id'], 'invalid statistics identity')
        windows, previous = _stats(index[key]['days'], asof)
        require(stat['windows'] == windows and stat['previous_observation'] == previous, 'statistics inconsistent with grid')
        stats_index[key] = stat
    require(set(stats_index) == set(index), 'missing statistics')
    found = set()
    for comp in document['comparisons']:
        fields(comp, 'canonical_id product_code_raw date price_104 price_109 volume_104 volume_109 absolute_gap relative_gap_pct comparison_status')
        crop = comp['product_code_raw']; require(crop in products and crop not in found and comp['canonical_id'] == products[crop] and comp['date'] == asof, 'invalid comparison identity'); found.add(crop)
        a,b = index['104',crop]['days'][-1],index['109',crop]['days'][-1]
        require((comp['price_104'],comp['price_109'],comp['volume_104'],comp['volume_109']) == (a['price_twd_per_kg'],b['price_twd_per_kg'],a['volume_kg'],b['volume_kg']), 'comparison values inconsistent')
        comparable = a['observation_status'] == b['observation_status'] == 'observed'
        require(comp['comparison_status'] == ('comparable' if comparable else 'not_comparable'), 'comparison status inconsistent')
        require(comp['absolute_gap'] == (round(a['price_twd_per_kg'] - b['price_twd_per_kg'],6) if comparable else None) and comp['relative_gap_pct'] == (round((a['price_twd_per_kg']/b['price_twd_per_kg']-1)*100,6) if comparable else None), 'comparison gap inconsistent')
    require(found == set(products), 'missing comparisons')
    quality = document['quality']; fields(quality, 'by_date_market calendar_conflicts observed_market_count observed_crop_count unplaced_markets valid_days_by_market')
    require(quality['unplaced_markets'] == sorted(m['market_code'] for m in document['geography']['markets'] if m['location_status'] != 'verified' or m['display_x'] is None or m['display_y'] is None), 'invalid unplaced markets')
    require(quality['valid_days_by_market'] == {code: len({d['date'] for (c,crop),s in index.items() if c == code for d in s['days'] if d['observation_status'] == 'observed'}) for code in ('104','109')}, 'invalid valid-day count')
    require(quality['calendar_conflicts'] == sum(d['calendar_conflict'] for s in document['series'] for d in s['days']), 'invalid conflict count')
    require(quality['observed_market_count'] == len({code for (code,crop),s in index.items() if s['days'][-1]['observation_status']=='observed'}), 'invalid market count')
    require(quality['observed_crop_count'] == len({crop for (code,crop),s in index.items() if s['days'][-1]['observation_status']=='observed'}), 'invalid crop count')
    for q in quality['by_date_market']:
        fields(q, 'date market_code observed fixture provenance_unknown invalid reasons'); _date(q['date'])
        require(q['date'] in dates and q['market_code'] in ('104','109') and all(isinstance(q[k],int) and not isinstance(q[k],bool) and q[k]>=0 for k in ('observed','fixture','provenance_unknown','invalid')) and isinstance(q['reasons'],dict), 'invalid quality')
    # Reject non-finite numbers even in fields not used by the cross-field calculations.
    try: json.dumps(document, allow_nan=False)
    except (ValueError, TypeError) as exc: raise TaipeiMapError('map contains non-finite or non-JSON value') from exc
    return document

def taipei_map_csv(document):
    validate_taipei_map(document)
    columns = ['data_mode','data_label','analysis_input_policy','requested_date','as_of_date','publication_status','market_code','canonical_id','product_code_raw','product_name_raw','date','price_twd_per_kg','volume_kg','observation_status','calendar_status','calendar_conflict','row_hash']
    out = io.StringIO(newline=''); writer = csv.DictWriter(out, fieldnames=columns, lineterminator='\n'); writer.writeheader()
    for series in document['series']:
        for day in series['days']:
            record = {k: series[k] for k in ('market_code','canonical_id','product_code_raw','product_name_raw')}
            record.update(day); record.update({k: document[k] for k in ('data_mode','requested_date','as_of_date','publication_status')}); record['analysis_input_policy'] = document['policy']['analysis_input_policy']; record['data_label'] = '合成測試資料' if document['data_mode'] == 'fixture' else '正式觀測資料'
            writer.writerow({k: '' if record[k] is None else record[k] for k in columns})
    return out.getvalue()
