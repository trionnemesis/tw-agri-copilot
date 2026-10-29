#!/usr/bin/env python3
"""Regenerate Taipei district SVG from the pinned municipal shapefile archive.

No network access is performed. Coordinates are retained in their native TWD97
TM2 (EPSG:3826) projection; shared boundaries receive the same transform and
rounding, without independent line simplification.
"""
import argparse
import hashlib
import json
import math
import pathlib
import struct
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_HASH = '77bcc347b503b8ff8a43f7e1afaaedb18877a6222282587b145adaba69afd2d9'
PREFIX = 'G97_A_CADIST_P'

def read_source(path):
    raw = pathlib.Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_HASH:
        raise ValueError('Unexpected boundary source hash')
    with zipfile.ZipFile(path) as z:
        prj = z.read(PREFIX + '.prj').decode('ascii')
        if 'Central_Meridian",121.0' not in prj or 'TWD_1997' not in prj:
            raise ValueError('Unexpected CRS')
        dbf, shp = z.read(PREFIX + '.dbf'), z.read(PREFIX + '.shp')
    count = struct.unpack_from('<I', dbf, 4)[0]
    header, size = struct.unpack_from('<HH', dbf, 8)
    fields = []
    for pos in range(32, header - 1, 32):
        field = dbf[pos:pos+32]
        fields.append((field[:11].split(b'\0')[0].decode('ascii'), field[16]))
    records = []
    for i in range(count):
        rec = dbf[header+i*size:header+(i+1)*size]; offset = 1; item = {}
        for name, width in fields:
            item[name] = rec[offset:offset+width].decode('utf8').strip(); offset += width
        records.append(item)
    polygons=[]; offset=100
    while offset < len(shp):
        _, length = struct.unpack_from('>ii', shp, offset); offset += 8
        record = shp[offset:offset+length*2]; offset += length*2
        if struct.unpack_from('<i',record,0)[0] != 5: raise ValueError('Expected polygon')
        parts, npoints = struct.unpack_from('<ii',record,36)
        starts=list(struct.unpack_from('<'+'i'*parts,record,44)) + [npoints]
        points=[struct.unpack_from('<dd',record,44+parts*4+j*16) for j in range(npoints)]
        polygons.append([points[starts[j]:starts[j+1]] for j in range(parts)])
    if len(records)!=12 or len(polygons)!=12: raise ValueError('Expected twelve districts')
    return prj, list(zip(records,polygons))

def create(path):
    prj, districts = read_source(path)
    points=[p for _, rings in districts for ring in rings for p in ring]
    minx=min(p[0] for p in points); maxx=max(p[0] for p in points)
    miny=min(p[1] for p in points); maxy=max(p[1] for p in points)
    scale=min(740/(maxx-minx),740/(maxy-miny)); ox=(800-(maxx-minx)*scale)/2; oy=(800-(maxy-miny)*scale)/2
    transform={'min_x':minx,'max_y':maxy,'scale':scale,'offset_x':ox,'offset_y':oy,'view_box':[0,0,800,800]}
    def project(p): return (ox+(p[0]-minx)*scale,oy+(maxy-p[1])*scale)
    result=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" role="img" aria-label="臺北市十二行政區">','<title>臺北市十二行政區</title>']
    seen=set()
    for rec,rings in sorted(districts,key=lambda x:x[0]['TNAME']):
        name=rec['TNAME']; code=rec['CPTID']
        if name in seen: raise ValueError('Duplicate district')
        seen.add(name); paths=[]
        for ring in rings:
            coords=[]
            for p in ring:
                x,y=project(p); s=f'{x:.0f},{y:.0f}'
                if not coords or s != coords[-1]: coords.append(s)
            if len(coords)>=3: paths.append('M'+' L'.join(coords)+' Z')
        result.append(f'<path id="district-{code}" data-name="{name}" fill-rule="evenodd" d="{" ".join(paths)}"/>')
    result.append('</svg>')
    return ('\n'.join(result)+'\n').encode(),prj,transform

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--source', default=ROOT/'data/geography/taipei/districts.zip'); parser.add_argument('--output',default=ROOT/'src/tpw/assets/taipei-districts.svg'); args=parser.parse_args()
    svg, prj, transform=create(args.source); pathlib.Path(args.output).write_bytes(svg)
    print(json.dumps({'sha256':hashlib.sha256(svg).hexdigest(),'bytes':len(svg),'source_crs_wkt':prj,'transform':transform},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
