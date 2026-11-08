"""Check atlas coverage and every generated GLB's indices, buffers and finite coordinates."""
import collections
import json
import math
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / 'public/explore'
catalog = json.loads((root/'src/explore/expanded-catalog.json').read_text(encoding='utf-8'))
assert len({o['id'] for o in catalog}) == len(catalog), 'Duplicate object IDs'
assert len([o for o in catalog if o['category'] == 'Constellation']) == 73
assert {f'm{i}' for i in range(1,111)} - {'m31','m45'} <= {o['id'] for o in catalog}
assert {'mercury','venus','mars','uranus','neptune','moon'} <= {o['id'] for o in catalog}
thumbnails = json.loads((out/'thumbnails/manifest.json').read_text(encoding='utf-8'))
expected = {o['id'] for o in catalog} | {'saturn','jupiter','vega','pleiades','andromeda'}
assert len(thumbnails) == len(expected) and {o['id'] for o in thumbnails} == expected
for thumbnail in thumbnails:
    preview = ET.parse(out/'thumbnails'/thumbnail['file']).getroot()
    assert preview.get('viewBox') == '0 0 400 300', thumbnail['id']
    assert preview.find('{http://www.w3.org/2000/svg}title') is not None, thumbnail['id']
    for element in preview.iter():
        assert element.tag != '{http://www.w3.org/2000/svg}script'
        assert all(not value.startswith(('http:', 'https:')) for key,value in element.attrib.items() if key.endswith('href'))
sizes = {5121:1,5123:2,5125:4,5126:4}
widths = {'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}
for object in catalog:
    assert (out/object['image']).is_file(), object['id']
    if object['image'].endswith('.svg'):
        ET.parse(out/object['image'])
for file in out.glob('*.glb'):
    raw = file.read_bytes()
    magic,version,length = struct.unpack_from('<III',raw)
    assert magic == 0x46546c67 and version == 2 and length == len(raw), file
    size,kind = struct.unpack_from('<II',raw,12)
    assert kind == 0x4e4f534a
    doc = json.loads(raw[20:20+size])
    # NASA models can use more accessor formats; full generated-geometry checks below.
    if file.stem in ('saturn','jupiter'):
        continue
    binary_offset = 20+size+8
    def values(accessor_index, fmt):
        accessor = doc['accessors'][accessor_index]
        view = doc['bufferViews'][accessor['bufferView']]
        count = accessor['count']*widths[accessor['type']]
        assert view.get('byteOffset',0)+view['byteLength'] <= doc['buffers'][0]['byteLength'], file
        assert count*sizes[accessor['componentType']] <= view['byteLength'], file
        start = binary_offset+view.get('byteOffset',0)+accessor.get('byteOffset',0)
        return struct.unpack_from('<'+fmt*count,raw,start)
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            positions = values(primitive['attributes']['POSITION'],'f')
            assert all(math.isfinite(v) for v in positions), file
            accessor = doc['accessors'][primitive['indices']]
            indices = values(primitive['indices'], {5123:'H',5125:'I'}[accessor['componentType']])
            assert len(indices) % 3 == 0 and max(indices) < len(positions)//3, file
print('Verified all local GLBs and generated SVG previews; 73 constellations and complete Messier coverage.')
print(f'Verified {len(thumbnails)} self-contained 2D thumbnails.')
print(dict(collections.Counter(o['category'] for o in catalog)))
