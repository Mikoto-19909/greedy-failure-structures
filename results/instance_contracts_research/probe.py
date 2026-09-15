"""Research-only, process-local extraction prototypes; never edits source files."""
import ast
import base64
import collections
import copy
import csv
import dataclasses
import importlib.abc
import importlib.util
import inspect
import io
import itertools
import json
import pickle
from pathlib import Path
import sys
import textwrap
import tokenize
import typing
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'src/maxcover/_instance_contracts.py'
MODE = sys.argv[1]
original = SOURCE.read_text(encoding='utf-8')
maps = original[original.index('P4_3_RESEARCH_QUESTION_IDS:'):original.index('\n\ndef _validate_instance_record_schema_version')]
helpers = original[original.index('def _record_parameter_int('):original.index('@dataclass(frozen=True, slots=True)\nclass InstanceRecord')]
family = original[original.index('        if self.family == "adversarial"'):original.index('\n    def to_csv_row(')]
exports = ['P4_3_RESEARCH_QUESTION_IDS', 'P4_3_INSTANCE_ORIGINS', 'P4_3_COUPLED_FAMILIES',
           '_record_parameter_int', '_record_parameter_number', '_require_record_parameter_keys',
           '_validate_p4_3_record_parameters', '_validate_paired_uniform_record_parameters']
leaf = '''from __future__ import annotations
import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ._instance_contracts import InstanceRecord

''' + maps + '\n\n' + helpers
modified = original
if MODE in {'stage1', 'stage2', 'inplace'}:
    if MODE in {'stage2','inplace'}:
        exports += ['_validate_instance_family']
        leaf += '\ndef _validate_instance_family(record: InstanceRecord, parameters: Mapping[str, object], certificate_values: tuple[object, ...]) -> None:\n'
        tokens=tokenize.generate_tokens(io.StringIO(textwrap.dedent(family)).readline)
        renamed=tokenize.untokenize(token._replace(string='record')
            if token.type==tokenize.NAME and token.string=='self' else token for token in tokens)
        leaf += textwrap.indent(renamed, '    ') + '\n'
        modified = modified.replace(family, '        _validate_instance_family(self, parameters, certificate_values)\n')
    if MODE == 'inplace':
        function = leaf[leaf.index('\ndef _validate_instance_family('):]
        modified = modified.replace('@dataclass(frozen=True, slots=True)\nclass InstanceRecord',function+'\n\n@dataclass(frozen=True, slots=True)\nclass InstanceRecord')
    else:
        modified = modified.replace(maps, 'from ._instance_family_validation import (\n' + ''.join('    '+n+',\n' for n in exports) + ')\n')
        modified = modified.replace(helpers, '')
elif MODE == 'reordered':
    line = '        _validate_instance_record_schema_version(self.schema_version)\n'
    modified = modified.replace(line, '', 1).replace('        if self.instance_origin not in', line+'        if self.instance_origin not in', 1)


class PrototypeLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'maxcover._instance_contracts' or (MODE in {'stage1', 'stage2'} and fullname == 'maxcover._instance_family_validation'):
            return importlib.util.spec_from_loader(fullname, self)
    def create_module(self, spec): return None
    def exec_module(self, module):
        code = modified if module.__name__.endswith('._instance_contracts') else leaf
        exec(compile(code, str(OUT / (MODE + '-' + module.__name__ + '.py')), 'exec'), module.__dict__)


sys.meta_path.insert(0, PrototypeLoader())
sys.path.insert(0, str(ROOT/'src'))
import maxcover
from maxcover import contracts
from maxcover._instance_contracts import InstanceRecord
from maxcover.benchmark import _instance_record, _instances_for_config
from maxcover.config import parse_config


def stable(value):
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def shape():
    return {'signature': str(inspect.signature(InstanceRecord)), 'fields': [f.name for f in dataclasses.fields(InstanceRecord)],
            'slots': list(InstanceRecord.__slots__), 'match_args': list(InstanceRecord.__match_args__),
            'csv_fields': list(InstanceRecord.CSV_FIELDS), 'module':InstanceRecord.__module__,
            'public_identity': maxcover.InstanceRecord is contracts.InstanceRecord is InstanceRecord,
            'frozen': InstanceRecord.__dataclass_params__.frozen}


def prepare():
    assert not (OUT/'inputs.json').exists(), 'Do not replace research inputs'
    with (ROOT/'tests/fixtures/benchmark_compatibility/instances.csv').open(encoding='utf-8', newline='') as f:
        corpus = [InstanceRecord.from_csv_row(r) for r in csv.DictReader(f)]
    selected = {}
    for record in corpus: selected.setdefault(record.family,record)
    for name in ('p4_fixed_size.json','p4_duplicate_heavy.json'):
        raw=json.loads((ROOT/'configs'/name).read_text(encoding='utf-8'))
        raw.update(repetitions=1, algorithms=[{'name':'greedy'}])
        for planned in _instances_for_config(parse_config(raw)):
            record=_instance_record(planned,'research-fixed-config')
            label=record.family+('-paired' if record.coupling_pair_id is not None else '')
            selected.setdefault(label,record)
    cases=[{'name':'legacy','family':'adversarial','block_size':4,'distractor_count':2},
           {'name':'unpaired-fixed','family':'fixed_size','universe_size':8,'set_count':4,'k':2,'set_size':2,'unique_sets':False},
           {'name':'unique-fixed','family':'fixed_size','universe_size':8,'set_count':4,'k':2,'set_size':2,'unique_sets':True}]
    for case in cases:
        config=parse_config({'schema_version':3,'name':case['name'],'base_seed':17,'repetitions':1,'algorithms':[{'name':'greedy'}],'cases':[case]})
        selected[case['name']]=_instance_record(_instances_for_config(config)[0],'research-fixed-config')
    selected['custom']=dataclasses.replace(selected['uniform'],family='external_custom',instance_origin='custom')
    inputs=[]
    for label,record in selected.items():
        inputs.append({'label':label,'kwargs':{f.name:getattr(record,f.name) for f in dataclasses.fields(record)},'csv':record.to_csv_row()})
    (OUT/'inputs.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2),encoding='utf-8')
    for protocol in (4,5):
        (OUT/f'old_instances_protocol{protocol}.pickle').write_bytes(pickle.dumps(list(selected.values()),protocol=protocol))
    print('Prepared',len(inputs),'representatives, no algorithm solve; existing corpus rows',len(corpus))


def evaluate():
    inputs=json.loads((OUT/'inputs.json').read_text(encoding='utf-8'))
    observations={}
    successful_lines=set()
    def trace(frame,event,arg):
        if event=='line' and frame.f_code.co_filename==str(OUT/(MODE+'-maxcover._instance_contracts.py')):
            successful_lines.add(frame.f_lineno)
        return trace
    def check(label,kwargs=None,row=None):
        before=copy.deepcopy(kwargs if kwargs is not None else row)
        try:
            record=InstanceRecord(**kwargs) if kwargs is not None else InstanceRecord.from_csv_row(row)
            value=['accepted',stable(record.to_csv_row()),hash(record)]
        except Exception as e:
            value=['rejected',type(e).__name__,str(e)]
        observations[label]=value
        # json NaN is not equal to itself, so compare serialized caller payloads.
        after=kwargs if kwargs is not None else row
        assert json.dumps(before,sort_keys=True)==json.dumps(after,sort_keys=True),(label,'caller mutated')
    for data in inputs:
        label=data['label']; kw=data['kwargs']; row={k:str(v) for k,v in data['csv'].items()}
        sys.settrace(trace)
        check(label+'/valid',kwargs=copy.deepcopy(kw))
        sys.settrace(None)
        check(label+'/csv-valid',row=copy.deepcopy(row))
        for key in kw:
            for index,value in enumerate([None,True,-1,0,1.0,'','invalid',[],float('nan'),float('inf')]):
                bad=copy.deepcopy(kw);bad[key]=value
                check(f'{label}/ctor/{key}/{index}',kwargs=bad)
        for key in row:
            for index,value in enumerate(['','True','-1','0','2.0','nan','invalid']):
                bad=dict(row);bad[key]=value
                check(f'{label}/csv/{key}/{index}',row=bad)
        parameters=json.loads(kw['parameters'])
        for key in parameters:
            for index,value in enumerate([None,True,-1,0,'bad',float('nan'),float('inf')]):
                p=copy.deepcopy(parameters);p[key]=value
                bad=copy.deepcopy(kw);bad['parameters']=json.dumps(p)
                check(f'{label}/parameter/{key}/{index}',kwargs=bad)
        for index,changes in enumerate([
            {'schema_version':99,'config_hash':''},
            {'repetition':True,'set_count':0},
            {'parameters':'bad json','actual_density':-1},
            {'actual_density':-1,'known_optimum':-1},
            {'optimum_selected':[True],'research_question_id':'bad'},
            {'generator_version':99,'parameters':'{}'},
        ]):
            bad=copy.deepcopy(kw);bad.update(changes);check(f'{label}/multi/{index}',kwargs=bad)
        # Canonicalization is an intended mutation of the new instance only.
        bad=copy.deepcopy(kw);bad['parameters']=json.dumps(parameters,indent=3,sort_keys=False)
        check(label+'/normalization-json',kwargs=bad)
        if kw['optimum_selected'] is not None:
            bad=copy.deepcopy(kw);bad['optimum_selected']=list(kw['optimum_selected'])
            check(label+'/normalization-selected',kwargs=bad)
    pickles={}
    for protocol in (4,5):
        values=pickle.loads((OUT/f'old_instances_protocol{protocol}.pickle').read_bytes())
        pickles[str(protocol)]=[stable(v.to_csv_row()) for v in values]
        assert all(type(v) is InstanceRecord for v in values)
        assert pickle.dumps(values,protocol=protocol)==(OUT/f'old_instances_protocol{protocol}.pickle').read_bytes()
    normal=InstanceRecord(**inputs[0]['kwargs'])
    try:normal.repetition=99
    except dataclasses.FrozenInstanceError:pass
    else:raise AssertionError('not frozen')
    payload=pickle.dumps(normal)
    with patch.object(InstanceRecord,'__post_init__',side_effect=AssertionError('unexpected validation')):
        pickle.loads(payload)
    with patch.object(InstanceRecord,'__post_init__',side_effect=AssertionError('replace revalidates')):
        try:dataclasses.replace(normal)
        except AssertionError as error:assert str(error)=='replace revalidates'
        else:raise AssertionError('replace skipped post init')
    import maxcover._instance_contracts as current
    hints={}
    for name in ('_validate_p4_3_record_parameters','_validate_paired_uniform_record_parameters'):
        try:typing.get_type_hints(getattr(current,name));hints[name]='passed'
        except Exception as e:hints[name]=type(e).__name__+': '+str(e)
    maps=getattr(current,'P4_3_RESEARCH_QUESTION_IDS')
    assert maps is contracts.P4_3_RESEARCH_QUESTION_IDS
    try:maps['x']='y'
    except TypeError:pass
    else:raise AssertionError('map not read-only')
    result={'mode':MODE,'cases':len(observations),'accepted':sum(v[0]=='accepted' for v in observations.values()),
            'shape':shape(),'outcomes':observations,'old_pickles':pickles,'private_type_hints':hints,
            'pickle_revalidates':False,'replace_revalidates':True,'valid_execution_lines':sorted(successful_lines),
            'source_lines':len(modified.splitlines()),'leaf_lines':len(leaf.splitlines()) if MODE in {'stage1','stage2'} else 0}
    result['public_type_hints'] = {name: {k: str(v) for k,v in typing.get_type_hints(value).items()}
        for name,value in [('InstanceRecord',InstanceRecord),('from_csv_row',InstanceRecord.from_csv_row)]}
    result['private_type_hints_with_namespace'] = {name: {k: str(v) for k,v in typing.get_type_hints(
        getattr(current,name),localns={'InstanceRecord':InstanceRecord}).items()}
        for name in ('_validate_p4_3_record_parameters','_validate_paired_uniform_record_parameters')}
    (OUT/(MODE+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(MODE,'cases',result['cases'],'accepted',result['accepted'],'source/leaf lines',result['source_lines'],result['leaf_lines'],'hints',hints)


if __name__=='__main__':
    prepare() if MODE=='prepare' else evaluate()
