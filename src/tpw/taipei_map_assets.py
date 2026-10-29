"""Strict, isolated Taipei map asset loader; no network access during builds."""
from __future__ import annotations

import csv
import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import zipfile
import xml.etree.ElementTree as ET

DISTRICTS = {'6300100':'松山區','6300200':'信義區','6300300':'大安區','6300400':'中山區','6300500':'中正區','6300600':'大同區','6300700':'萬華區','6300800':'文山區','6300900':'南港區','6301000':'內湖區','6301100':'士林區','6301200':'北投區'}


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _tm2(lon, lat):
    """WGS84 lon/lat to TWD97 TM2, GRS80, 121° central meridian (metres)."""
    a=6378137.0; f=1/298.257222101; e2=f*(2-f); ep=e2/(1-e2); k=0.9999
    phi=math.radians(lat); lam=math.radians(lon-121); n=a/math.sqrt(1-e2*math.sin(phi)**2)
    t=math.tan(phi)**2; c=ep*math.cos(phi)**2; aa=math.cos(phi)*lam
    m=a*((1-e2/4-3*e2**2/64-5*e2**3/256)*phi-(3*e2/8+3*e2**2/32+45*e2**3/1024)*math.sin(2*phi)+(15*e2**2/256+45*e2**3/1024)*math.sin(4*phi)-(35*e2**3/3072)*math.sin(6*phi))
    x=250000+k*n*(aa+(1-t+c)*aa**3/6+(5-18*t+t*t+72*c-58*ep)*aa**5/120)
    y=k*(m+n*math.tan(phi)*(aa**2/2+(5-t+9*c+4*c*c)*aa**4/24+(61-58*t+t*t+600*c-330*ep)*aa**6/720))
    return x,y


def _district_contains(archive, code, point):
    """Test the point against the original, unrounded SHP polygon in metres."""
    with zipfile.ZipFile(archive) as z:
        dbf=z.read('G97_A_CADIST_P.dbf'); shp=z.read('G97_A_CADIST_P.shp')
    count=struct.unpack_from('<I',dbf,4)[0]; header,size=struct.unpack_from('<HH',dbf,8)
    fields=[]
    for i in range(32,header-1,32):
        f=dbf[i:i+32]; fields.append((f[:11].split(b'\0')[0].decode('ascii'), f[16]))
    codes=[]
    for i in range(count):
        record=dbf[header+i*size:header+(i+1)*size]; offset=1; values={}
        for name,width in fields:
            values[name]=record[offset:offset+width].decode('utf-8').strip(); offset+=width
        codes.append(values['CPTID'])
    offset=100; index=0; x,y=point
    while offset<len(shp):
        _,length=struct.unpack_from('>ii',shp,offset); offset+=8
        record=shp[offset:offset+length*2]; offset+=length*2
        if codes[index]==code:
            if struct.unpack_from('<i',record,0)[0]!=5: raise ValueError('Invalid district geometry')
            parts,npoints=struct.unpack_from('<ii',record,36)
            starts=list(struct.unpack_from('<'+'i'*parts,record,44))+[npoints]
            points=[struct.unpack_from('<dd',record,44+parts*4+j*16) for j in range(npoints)]
            inside=False
            for part in range(parts):
                ring=points[starts[part]:starts[part+1]]
                for (x1,y1),(x2,y2) in zip(ring,ring[1:]+ring[:1]):
                    if (y1>y)!=(y2>y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1: inside=not inside
            return inside
        index+=1
    return False


def validate_svg(svg):
    if len(svg)>150*1024: raise ValueError('Taipei SVG exceeds size budget')
    try: root=ET.fromstring(svg)
    except ET.ParseError as exc: raise ValueError('Invalid Taipei SVG') from exc
    ns='{http://www.w3.org/2000/svg}'
    if root.tag != ns+'svg' or root.attrib != {'viewBox':'0 0 800 800','role':'img','aria-label':'臺北市十二行政區'}: raise ValueError('Invalid SVG root')
    found={}
    for child in root:
        if child.tag == ns+'title':
            if child.attrib or list(child): raise ValueError('Invalid title')
        elif child.tag == ns+'path':
            if set(child.attrib)!={'id','data-name','fill-rule','d'} or child.attrib['fill-rule']!='evenodd' or list(child): raise ValueError('Invalid SVG path')
            code=child.attrib['id'].removeprefix('district-')
            if child.attrib['id']!='district-'+code or code not in DISTRICTS or child.attrib['data-name'] != DISTRICTS[code] or code in found: raise ValueError('Invalid district identity')
            if not re.fullmatch(r'[MLZ0-9., -]+',child.attrib['d']): raise ValueError('Invalid SVG path data')
            found[code]=True
        else: raise ValueError('Unsafe SVG element')
    if set(found)!=set(DISTRICTS): raise ValueError('Missing districts')


def load_taipei_map_assets(root):
    """Return (geography, geometry metadata, safe SVG text), failing closed."""
    root=Path(root)
    geo=json.loads((root/'config/taipei-market-geography.json').read_text(encoding='utf-8'))
    geometry=json.loads((root/'config/taipei-boundary-source.json').read_text(encoding='utf-8'))
    registry=json.loads((root/'config/official-produce-markets.json').read_text(encoding='utf-8'))
    svg=(root/'src/tpw/assets/taipei-districts.svg').read_bytes()
    validate_svg(svg)
    if geometry['source_sha256'] != '77bcc347b503b8ff8a43f7e1afaaedb18877a6222282587b145adaba69afd2d9' or geometry['output_sha256'] != 'd9a5c569044d9ff40a869851cfb46b8e22b0bda3aa35528af12da393eb17e061' or geo['source_sha256'] != '316d152b18e41a3b5835508e94607789064e57c6c9f2f4a1e2e3c87182633655': raise ValueError('Unreviewed Taipei source or asset')
    expected_transform={'min_x':296266.05303026026,'max_y':2789176.169387096,'scale':0.02675220295351135,'offset_x':120.02204168251922,'offset_y':30.0,'view_box':[0,0,800,800]}
    if geometry['transform'] != expected_transform: raise ValueError('Invalid display transform')
    if _hash(svg)!=geometry['output_sha256'] or _hash((root/'data/geography/taipei/districts.zip').read_bytes())!=geometry['source_sha256'] or _hash((root/'data/geography/taipei/markets.csv').read_bytes())!=geo['source_sha256']: raise ValueError('Taipei source or output hash mismatch')
    if geometry['source_crs']!='EPSG:3826' or geometry['output_crs']!='EPSG:3826' or 'Central_Meridian",121.0' not in geometry['source_crs_wkt']: raise ValueError('Invalid Taipei CRS')
    geo_keys={'schema_version','dataset_url','resource_url','source_path','source_sha256','downloaded_at','license','license_url','markets'}
    if set(geo)!=geo_keys or geo['schema_version']!='1.0': raise ValueError('Invalid geography fields')
    datetime.date.fromisoformat(geo['downloaded_at'])
    registry_map={m['market_code']:m for m in registry['markets']}
    with (root/'data/geography/taipei/markets.csv').open(encoding='cp950', newline='') as source:
        source_rows={row['stitle']:row for row in csv.DictReader(source)}
    markets=geo['markets']
    if len(markets)!=2 or {m['market_code'] for m in markets}!={'104','109'}: raise ValueError('Invalid market crosswalk')
    for market in markets:
        expected={'market_namespace','market_code','official_name','district_code','district_name','reference_address','operating_address','longitude','latitude','coordinate_crs','location_role','location_status','valid_from','valid_to','valid_time_precision','verified_at','address_evidence_url','coordinate_evidence_url','source_snapshot_hash','location_note'}
        if set(market)!=expected: raise ValueError('Invalid market fields')
        code=market['market_code']
        if market['market_namespace']!='moa_market_8066' or market['official_name']!=registry_map[code]['official_name'] or DISTRICTS.get(market['district_code'])!=market['district_name']: raise ValueError('Invalid market identity')
        if market['location_status'] not in ('verified','conflicting_sources','unverified') or market['location_role'] not in ('operating_site','reference_site') or market['coordinate_crs']!='EPSG:4326': raise ValueError('Invalid market location status')
        source_row=source_rows[market['official_name']]
        if market['source_snapshot_hash'] != geo['source_sha256'] or market['reference_address'] != source_row['xAddress'] or market['longitude'] != float(source_row['GTag_longitude']) or market['latitude'] != float(source_row['GTag_latitude']): raise ValueError('Market coordinate does not match source row')
        if market['valid_time_precision'] not in ('unknown','day','month','year'): raise ValueError('Invalid time precision')
        for key in ('verified_at','valid_from','valid_to'):
            if market[key] is not None: datetime.date.fromisoformat(market[key])
        if market['valid_from'] and market['valid_to'] and market['valid_from'] > market['valid_to']: raise ValueError('Invalid location interval')
        lon=market['longitude']; lat=market['latitude']
        if lon is not None or lat is not None:
            if not isinstance(lon,(int,float)) or not isinstance(lat,(int,float)) or not (121.4 < lon < 121.7 and 24.9 < lat < 25.3): raise ValueError('Invalid longitude or latitude')
        market['display_x']=market['display_y']=None
        if market['location_status']=='verified':
            if market['location_role']!='operating_site' or lon is None or market['operating_address'] != market['reference_address']: raise ValueError('Verified market missing operating location')
            x,y=_tm2(lon,lat)
            if not _district_contains(root/'data/geography/taipei/districts.zip', market['district_code'], (x,y)): raise ValueError('Market is outside claimed district')
            t=geometry['transform']
            market['display_x']=round(t['offset_x']+(x-t['min_x'])*t['scale'],2)
            market['display_y']=round(t['offset_y']+(t['max_y']-y)*t['scale'],2)
            if not 0<=market['display_x']<=800 or not 0<=market['display_y']<=800: raise ValueError('Market outside view')
    return geo, geometry, svg.decode('utf-8')
