import copy
import json
from pathlib import Path
import unittest
from tpw.taipei_map import failed_taipei_map, validate_taipei_map, TaipeiMapError, taipei_map_csv

class MapContractTest(unittest.TestCase):
    def test_failed_document_has_no_stale_values_and_mode_is_enforced(self):
        pub={'requested_date':'2026-10-29','resolved_date':'2026-10-21','status':'source_unavailable'}
        doc=failed_taipei_map('2026-10-21',pub,'asset damaged','fixture')
        self.assertEqual(doc['series'],[]); self.assertIsNone(doc['inputs']); self.assertIn('data_label', taipei_map_csv(doc).splitlines()[0])
        with self.assertRaises(TaipeiMapError): validate_taipei_map(doc,'observed')
        bad=copy.deepcopy(doc); bad['series']=[{'price_twd_per_kg':20}]
        with self.assertRaises(TaipeiMapError): validate_taipei_map(bad)
    def test_schema_has_failure_branch(self):
        schema=json.loads((Path(__file__).resolve().parents[2]/'schema/taipei-map.schema.json').read_text())
        self.assertFalse(schema['additionalProperties']); self.assertIn('analysis_status',schema['required']); self.assertTrue(schema['allOf'])

def _schema_accepts(schema, value):
    """Exercise the schema vocabulary used here without a runtime dependency."""
    import math
    import re
    if 'const' in schema and value != schema['const']: return False
    if 'enum' in schema and value not in schema['enum']: return False
    if 'anyOf' in schema and not any(_schema_accepts(sub,value) for sub in schema['anyOf']): return False
    kind=schema.get('type')
    types={'object':lambda x:isinstance(x,dict), 'array':lambda x:isinstance(x,list),
           'string':lambda x:isinstance(x,str), 'null':lambda x:x is None,
           'integer':lambda x:isinstance(x,int) and not isinstance(x,bool),
           'number':lambda x:isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x),
           'boolean':lambda x:isinstance(x,bool)}
    if kind and not types[kind](value): return False
    if isinstance(value,dict):
        props=schema.get('properties',{})
        if any(k not in value for k in schema.get('required',[])): return False
        if schema.get('additionalProperties') is False and any(k not in props for k in value): return False
        for k,v in value.items():
            rule=props.get(k,schema.get('additionalProperties',{}))
            if isinstance(rule,dict) and not _schema_accepts(rule,v): return False
    if isinstance(value,list):
        if len(value)>schema.get('maxItems',float('inf')): return False
        if not all(_schema_accepts(schema.get('items',{}),v) for v in value): return False
    if isinstance(value,str):
        if len(value)<schema.get('minLength',0) or ('pattern' in schema and not re.search(schema['pattern'],value)): return False
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        if value < schema.get('minimum',-float('inf')) or value <= schema.get('exclusiveMinimum',-float('inf')): return False
    for sub in schema.get('allOf',[]):
        if 'if' in sub:
            branch=sub.get('then',{}) if _schema_accepts(sub['if'],value) else sub.get('else',{})
            if not _schema_accepts(branch,value): return False
        elif not _schema_accepts(sub,value): return False
    return True

class SchemaConsistencyTest(unittest.TestCase):
    def test_valid_and_invalid_documents(self):
        from tests.unit.test_taipei_map import MapDataTest
        helper=MapDataTest(); helper.setUp(); self.addCleanup(helper.doCleanups)
        published=helper.build([helper.row('2026-08-25','104',20,10)])
        failed=failed_taipei_map('2026-08-25',helper.pub,'damaged')
        schema=json.loads((Path(__file__).resolve().parents[2]/'schema/taipei-map.schema.json').read_text())
        for doc in (published,failed):
            self.assertTrue(_schema_accepts(schema,doc)); validate_taipei_map(doc)
        for doc in (published,failed):
            bad=copy.deepcopy(doc); bad['unexpected']=1
            self.assertFalse(_schema_accepts(schema,bad))
            with self.assertRaises(TaipeiMapError): validate_taipei_map(bad)
        bad=copy.deepcopy(published); bad['geography']['markets'][0]['unexpected']=1
        self.assertFalse(_schema_accepts(schema,bad))
        with self.assertRaises(TaipeiMapError): validate_taipei_map(bad)
