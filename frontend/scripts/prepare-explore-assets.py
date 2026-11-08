"""Reproduce locally served Explore assets. Python standard library only.

NASA models/images are unchanged downloads. Generated GLBs are schematics.
HYG angular coordinates are retained; cluster depth and star radii are illustrative.
"""
import csv
import gzip
import hashlib
import io
import json
import math
import random
import re
import struct
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'public/explore'
CACHE = ROOT / 'scripts/.cache'
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)


def fetch(url, target):
    if not target.exists():
        request = urllib.request.Request(url, headers={'User-Agent': 'Pleiades/1.0 astronomy education'})
        with urllib.request.urlopen(request, timeout=40) as response:
            target.write_bytes(response.read())
    return target.read_bytes()


def preview(page):
    request = urllib.request.Request(page, headers={'User-Agent': 'Pleiades/1.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read().decode('utf-8')
    match = re.search(r'<meta property="og:image" content="([^"]+)', content)
    if not match:
        raise ValueError('Reference image not found on ' + page)
    return match.group(1).replace('&amp;', '&')


def glb(name, positions, indices, colors, nodes=None):
    binary = bytearray()
    views, accessors = [], []

    def add(values, fmt, components, kind, target):
        while len(binary) % 4:
            binary.append(0)
        start = len(binary)
        flat = [x for row in values for x in row] if components > 1 else values
        binary.extend(struct.pack('<' + fmt * len(flat), *flat))
        views.append({'buffer': 0, 'byteOffset': start, 'byteLength': len(binary) - start, 'target': target})
        component_type = {'f': 5126, 'H': 5123, 'B': 5121}[fmt]
        accessor = {'bufferView': len(views) - 1, 'componentType': component_type, 'count': len(values), 'type': kind}
        if kind == 'VEC3':
            accessor['min'] = [min(row[i] for row in values) for i in range(3)]
            accessor['max'] = [max(row[i] for row in values) for i in range(3)]
        if fmt == 'B':
            accessor['normalized'] = True
        accessors.append(accessor)
        return len(accessors) - 1

    p = add(positions, 'f', 3, 'VEC3', 34962)
    ix = add(indices, 'H', 1, 'SCALAR', 34963)
    c = add(colors, 'B', 4, 'VEC4', 34962)
    nodes = nodes or [{'mesh': 0}]
    document = {'asset': {'version': '2.0', 'generator': 'Pleiades educational schematic generator'},
                'extensionsUsed': ['KHR_materials_unlit'], 'scene': 0,
                'scenes': [{'nodes': list(range(len(nodes)))}], 'nodes': nodes,
                'meshes': [{'primitives': [{'attributes': {'POSITION': p, 'COLOR_0': c}, 'indices': ix, 'material': 0}]}],
                'materials': [{'extensions': {'KHR_materials_unlit': {}}, 'doubleSided': True,
                               'pbrMetallicRoughness': {'baseColorFactor': [1, 1, 1, 1], 'metallicFactor': 0}}],
                'buffers': [{'byteLength': len(binary)}], 'bufferViews': views, 'accessors': accessors}
    encoded = json.dumps(document, separators=(',', ':')).encode()
    encoded += b' ' * (-len(encoded) % 4)
    binary.extend(b'\x00' * (-len(binary) % 4))
    packed = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(encoded) + 8 + len(binary))
    packed += struct.pack('<II', len(encoded), 0x4E4F534A) + encoded
    packed += struct.pack('<II', len(binary), 0x004E4942) + binary
    (OUT / name).write_bytes(packed)


def sphere():
    positions, colors, indices = [], [], []
    for j in range(25):
        theta = math.pi * j / 24
        for i in range(49):
            phi = 2 * math.pi * i / 48
            x, y, z = math.sin(theta) * math.cos(phi), math.cos(theta), math.sin(theta) * math.sin(phi)
            positions.append([x, y, z])
            brightness = .70 + .30 * ((z + 1) / 2)
            colors.append([int(175 * brightness), int(208 * brightness), int(255 * brightness), 255])
    for j in range(24):
        for i in range(48):
            a, b = j * 49 + i, (j + 1) * 49 + i
            indices.extend([a, b, a + 1, a + 1, b, b + 1])
    return positions, indices, colors


def make_cluster(stars):
    positions, indices, colors = sphere()
    mean_ra = sum(s['ra_hours'] for s in stars) / len(stars)
    mean_dec = sum(s['dec_deg'] for s in stars) / len(stars)
    nodes = []
    for i, star in enumerate(stars):
        x = -(star['ra_hours'] - mean_ra) * 15 * math.cos(math.radians(mean_dec)) * 2
        y = (star['dec_deg'] - mean_dec) * 2
        radius = .075 + max(0, 6 - star['magnitude']) * .035
        nodes.append({'mesh': 0, 'name': star['name'], 'translation': [x, y, (i % 3 - 1) * .25],
                      'scale': [radius] * 3})
    glb('pleiades.glb', positions, indices, colors, nodes)


def make_galaxy():
    rng = random.Random(45)
    positions, indices, colors = [], [], []
    octahedron = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
    faces = [0, 2, 4, 2, 1, 4, 1, 3, 4, 3, 0, 4, 2, 0, 5, 1, 2, 5, 3, 1, 5, 0, 3, 5]
    for i in range(1500):
        radius = rng.random() ** .7 * 3.8
        angle = i % 3 * 2 * math.pi / 3 + radius * 1.4 + rng.gauss(0, .15)
        x, z = radius * math.cos(angle), radius * math.sin(angle)
        y = rng.gauss(0, .025 + .05 * (1 - radius / 4))
        size = rng.uniform(.012, .033) * (1.6 if radius < .8 else 1)
        color = [255, 210, 145, 255] if radius < 1.3 else [170, 200, 255, 255]
        offset = len(positions)
        positions.extend([[x + a * size, y + b * size, z + c * size] for a, b, c in octahedron])
        indices.extend(offset + n for n in faces)
        colors.extend([color] * 6)
    glb('andromeda-illustration.glb', positions, indices, colors,
        [{'mesh': 0, 'rotation': [.258819, 0, 0, .965926]}])


if __name__ == '__main__':
    sources = []
    assets = [
        ('saturn', 'https://assets.science.nasa.gov/content/dam/science/psd/solar/2023/09/s/Saturn_1_120536.glb',
         'https://science.nasa.gov/resource/saturn-3d-model/', 'NASA VTAD'),
        ('jupiter', 'https://assets.science.nasa.gov/content/dam/science/psd/solar/2023/09/j/Jupiter_1_142984.glb',
         'https://science.nasa.gov/resource/jupiter-3d-model/', 'NASA VTAD'),
    ]
    for name, model, page, credit in assets:
        payload = fetch(model, OUT / (name + '.glb'))
        if payload[:4] != b'glTF':
            raise ValueError('Expected a GLB model')
        reference_page = 'https://science.nasa.gov/' + name + '/'
        image_url = preview(reference_page)
        fetch(image_url, OUT / (name + '.jpg'))
        sources.append({'asset': name, 'page': page, 'model_url': model, 'image_url': image_url,
                        'reference_page': reference_page, 'credit': credit,
                        'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()})
    for name, page, credit in [
        ('pleiades', 'https://science.nasa.gov/photojournal/seven-sisters-get-wise/', 'NASA/JPL-Caltech/UCLA; infrared WISE image'),
        ('andromeda', 'https://science.nasa.gov/photojournal/andromeda/', 'NASA/JPL-Caltech; ultraviolet GALEX image'),
    ]:
        image_url = preview(page)
        fetch(image_url, OUT / (name + '.jpg'))
        sources.append({'asset': name, 'page': page, 'image_url': image_url, 'credit': credit})
    catalog_url = 'https://raw.githubusercontent.com/astronexus/HYG-Database/main/hyg/CURRENT/hygdata_v40.csv.gz'
    catalog = fetch(catalog_url, CACHE / 'hygdata_v40.csv.gz')
    names = {'Alcyone', 'Atlas', 'Electra', 'Maia', 'Merope', 'Taygeta', 'Pleione', 'Celaeno', 'Asterope', 'Vega'}
    found = []
    for row in csv.DictReader(io.StringIO(gzip.decompress(catalog).decode('utf-8'))):
        if row['proper'] in names:
            found.append({'name': row['proper'], 'ra_hours': float(row['ra']), 'dec_deg': float(row['dec']), 'magnitude': float(row['mag'])})
    stars = [s for s in found if s['name'] != 'Vega']
    if len(stars) < 7:
        raise ValueError('Insufficient verified Pleiades members')
    catalog_json = json.dumps({'source': catalog_url, 'license': 'CC BY-SA 4.0',
        'epoch': 'J2000', 'stars': found, 'cluster_depth': 'illustrative; not a measured 3-D reconstruction'}, indent=2) + '\n'
    (OUT / 'star-catalog.json').write_text(catalog_json)
    (OUT.parent.parent / 'src' / 'explore' / 'star-catalog.json').write_text(catalog_json)
    glb('vega-illustration.glb', *sphere())
    make_cluster(stars)
    make_galaxy()
    (OUT / 'sources.json').write_text(json.dumps({'sources': sources, 'catalog_url': catalog_url,
        'catalog_credit': 'David Nash / Astronexus, HYG v4.0, CC BY-SA 4.0',
        'generated_models': 'Pleiades: angular layout from HYG, schematic depth/enlarged stars, CC BY-SA 4.0. Vega and galaxy: original educational illustrations, CC BY 4.0.'}, indent=2) + '\n')
    print('Prepared local models, reference images, and verified star coordinates.')
