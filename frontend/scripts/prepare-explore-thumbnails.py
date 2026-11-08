"""Build a local, standalone 2D SVG thumbnail for every atlas object; no network required.

Uses original vector illustrations and catalog-derived layouts. The lunar illustration
embeds the attributed NASA SVS texture. Detail reference images are preserved.
"""
import base64
import html
import json
import math
import random
import shutil
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT/'public/explore'
OUT = ASSETS/'thumbnails'
OUT.mkdir(exist_ok=True)
expanded = json.loads((ROOT/'src/explore/expanded-catalog.json').read_text(encoding='utf-8'))
objects = [dict(id=id,name=name,category=category,model=model) for id,name,category,model in [
    ('saturn','Saturn','Planet','saturn.glb'),('jupiter','Jupiter','Planet','jupiter.glb'),
    ('vega','Vega','Star','vega-illustration.glb'),('pleiades','Pleiades','Star cluster','pleiades.glb'),
    ('andromeda','Andromeda Galaxy','Galaxy','andromeda-illustration.glb')]]+expanded


def svg(title, content, definitions=''):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="400" height="300">
<title>{html.escape(title)} — 2D educational preview</title>
<defs><radialGradient id="bg"><stop stop-color="#1b2b46"/><stop offset="1" stop-color="#060b17"/></radialGradient>{definitions}</defs>
<path d="M0 0h400v300H0z" fill="url(#bg)"/>{content}</svg>'''


def attributes(model):
    raw = (ASSETS/model).read_bytes()
    size = struct.unpack_from('<I',raw,12)[0]
    document = json.loads(raw[20:20+size])
    binary = 28+size
    attrs = document['meshes'][0]['primitives'][0]['attributes']
    def read(key,fmt,width):
        accessor = document['accessors'][attrs[key]]
        view = document['bufferViews'][accessor['bufferView']]
        offset = binary+view.get('byteOffset',0)+accessor.get('byteOffset',0)
        count = accessor['count']*width
        return struct.unpack_from('<'+fmt*count,raw,offset)
    return read('POSITION','f',3),read('COLOR_0','B',4)


def planet(object):
    id = object['id']
    colors = {'mercury':('#c8bdb1','#746a63'),'venus':('#f8ddb0','#c18e4c'),
              'mars':('#edb187','#9e4730'),'jupiter':('#f4dec2','#b47f61'),
              'saturn':('#f4e3b5','#b69b69'),'uranus':('#c8f4ed','#6ebcc7'),
              'neptune':('#8db9ff','#2748af'),'moon':('#e6e5dc','#8a8b88')}
    pale,dark = colors[id]
    radius = 82 if id == 'saturn' else 106
    defs = f'<clipPath id="disk"><circle cx="200" cy="150" r="{radius}"/></clipPath><radialGradient id="surface" cx="32%" cy="25%" r="78%"><stop stop-color="{pale}"/><stop offset=".65" stop-color="{dark}"/><stop offset="1" stop-color="#101423"/></radialGradient><radialGradient id="shade" cx="25%" cy="20%" r="85%"><stop offset=".45" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#010611" stop-opacity=".86"/></radialGradient>'
    rng = random.Random(id)
    details = ''
    if id == 'moon':
        texture = base64.b64encode((ASSETS/'moon-color.jpg').read_bytes()).decode()
        details = f'<image x="-12" y="44" width="424" height="212" preserveAspectRatio="none" href="data:image/jpeg;base64,{texture}"/>'
    elif id in ('mercury','mars'):
        for _ in range(100):
            x,y,r = rng.uniform(95,305),rng.uniform(44,256),rng.uniform(1,10)
            details += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{dark}" fill-opacity=".3" stroke="{pale}" stroke-opacity=".35" stroke-width=".8"/>'
        if id == 'mars':
            details += '<ellipse cx="188" cy="49" rx="33" ry="9" fill="#f1eddb" opacity=".7"/>'
    else:
        for i in range(24):
            y = 45+i*9
            wave = rng.uniform(-5,5)
            details += f'<path d="M80 {y} Q200 {y+wave:.1f} 320 {y-2}" fill="none" stroke="{pale if i%3 else dark}" stroke-opacity="{.08 if id in ("uranus","neptune") else .24}" stroke-width="{rng.uniform(2,8):.1f}"/>'
        if id == 'jupiter':
            details += '<ellipse cx="231" cy="182" rx="25" ry="12" fill="#b25d43" opacity=".9"/><ellipse cx="230" cy="182" rx="19" ry="8" fill="#df9877"/>'
        if id == 'neptune':
            details += '<ellipse cx="231" cy="174" rx="17" ry="7" fill="#254d9b" opacity=".6"/>'
    ring = '<ellipse cx="200" cy="150" rx="169" ry="45" fill="none" stroke="#c8b58e" stroke-width="22" opacity=".85" transform="rotate(-23 200 150)"/><ellipse cx="200" cy="150" rx="169" ry="45" fill="none" stroke="#242839" stroke-width="3" transform="rotate(-23 200 150)"/>' if id == 'saturn' else ''
    content = ring+f'<circle cx="200" cy="150" r="{radius}" fill="url(#surface)"/><g clip-path="url(#disk)">{details}<circle cx="200" cy="150" r="{radius}" fill="url(#shade)"/></g>'
    if ring:
        content += '<path d="M43 214 Q200 222 356 86" fill="none" stroke="#d6c4a1" stroke-width="11" opacity=".8"/>'
    return svg(object['name'],content,defs)


def star(object):
    _,colors = attributes(object['model'])
    color = f'rgb{tuple(colors[:3])}'
    defs = f'<radialGradient id="halo"><stop stop-color="{color}" stop-opacity=".85"/><stop offset=".3" stop-color="{color}" stop-opacity=".24"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient><radialGradient id="star" cx="37%" cy="30%"><stop stop-color="#fff"/><stop offset=".65" stop-color="{color}"/><stop offset="1" stop-color="{color}" stop-opacity=".7"/></radialGradient>'
    return svg(object['name'],f'<circle cx="200" cy="150" r="119" fill="url(#halo)"/><path d="M200 58v184M108 150h184" stroke="{color}" stroke-width="1" opacity=".3"/><circle cx="200" cy="150" r="37" fill="url(#star)"/>',defs)


def galaxy(object):
    p,c = attributes(object['model'])
    # Generated galaxy stars have six vertices each. Project the disk at an angle
    # so its structure reads clearly in a small card, rather than edge-on.
    points = []
    for i in range(0,min(len(p)//3,2400*6),18):
        x,y,z = p[i*3:i*3+3]
        points.append((x*.94+z*.34, y*.8+z*.58-x*.12,c[i*4:i*4+3]))
    extent = max(max(abs(x),abs(y)) for x,y,_ in points)+.2
    dots = ''.join(f'<circle cx="{200+x/extent*166:.2f}" cy="{150-y/extent*132:.2f}" r="{.55+(i%4)*.12:.2f}" fill="rgb{tuple(color)}" opacity=".85"/>' for i,(x,y,color) in enumerate(points))
    defs = '<radialGradient id="galaxy"><stop stop-color="#ffe1ad" stop-opacity=".85"/><stop offset=".2" stop-color="#d2c5c0" stop-opacity=".35"/><stop offset=".6" stop-color="#7498d9" stop-opacity=".16"/><stop offset="1" stop-color="#668ad3" stop-opacity="0"/></radialGradient>'
    return svg(object['name'],'<ellipse cx="200" cy="150" rx="173" ry="102" fill="url(#galaxy)"/>'+dots,defs)


for object in objects:
    id = object['id']
    target = OUT/(id+'.svg')
    category = object['category']
    if category in ('Planet','Moon'):
        artwork = planet(object)
    elif category == 'Star':
        artwork = star(object)
    elif category == 'Galaxy':
        artwork = galaxy(object)
    else:
        # These existing original 2D assets retain catalog angular patterns and
        # cloud illustrations, unlike the separate photographic detail images.
        source = ASSETS/(id+'.svg')
        shutil.copyfile(source,target)
        continue
    target.write_text(artwork,encoding='utf-8')
(OUT/'manifest.json').write_text(json.dumps([dict(id=o['id'],file=o['id']+'.svg',alt='2D preview of '+o['name']) for o in objects],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Prepared {len(objects)} standalone 2D thumbnails.')
