"""Build the year-round WNY atlas. Standard library only; deterministic GLB/SVG assets.

Downloads are cached. Constellation figures/bounds and Messier positions: d3-celestial.
Stars: HYG v4.0. Geometry is educational, with enhanced color and schematic depth.
Run after prepare-explore-assets.py; existing NASA Saturn/Jupiter assets are retained.
"""
import csv
import gzip
import html
import importlib.util
import io
import json
import math
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('assets', ROOT / 'scripts/prepare-explore-assets.py')
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)
OUT, CACHE = assets.OUT, assets.CACHE
DATA_URL = 'https://raw.githubusercontent.com/ofrohn/d3-celestial/master/'
for filename in ['constellations.lines.json', 'constellations.bounds.json', 'constellations.json', 'messier.json']:
    assets.fetch(DATA_URL + 'data/' + filename, CACHE / filename)
assets.fetch(DATA_URL + 'LICENSE', CACHE / 'd3-celestial-LICENSE')
shutil.copyfile(CACHE / 'd3-celestial-LICENSE', OUT / 'd3-celestial-LICENSE.txt')
moon_texture_url = 'https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/lroc_color_2k.jpg'
moon_texture = assets.fetch(moon_texture_url, CACHE/'moon-color.jpg')
shutil.copyfile(CACHE/'moon-color.jpg', OUT/'moon-color.jpg')


def data(name):
    return json.loads((CACHE / name).read_text(encoding='utf-8'))['features']


class Scene:
    def __init__(self):
        self.p, self.i, self.c, self.dots, self.fog, self.segments = [], [], [], [], [], []

    def ball(self, xyz, radius, color):
        # Small round stars, shared in one mesh for efficient rendering.
        offset = len(self.p)
        if radius < .045:
            vertices = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
            self.p.extend([[xyz[k]+radius*p[k] for k in range(3)] for p in vertices])
            self.c.extend([list(color[:3])+[255]]*6)
            self.i.extend(offset+n for n in [0,2,4,2,1,4,1,3,4,3,0,4,2,0,5,1,2,5,3,1,5,0,3,5])
            self.dots.append((xyz[0],xyz[1],radius,color))
            return
        for j in range(7):
            t = math.pi * j / 6
            for k in range(11):
                a = 2 * math.pi * k / 10
                self.p.append([xyz[0] + radius * math.sin(t) * math.cos(a),
                               xyz[1] + radius * math.cos(t), xyz[2] + radius * math.sin(t) * math.sin(a)])
                self.c.append(list(color[:3]) + [255])
        for j in range(6):
            for k in range(10):
                a = offset + j * 11 + k
                self.i.extend([a, a + 11, a + 1, a + 1, a + 11, a + 12])
        self.dots.append((xyz[0], xyz[1], radius, color))

    def line(self, a, b, color=(80, 150, 230)):
        # Thin six-sided tube, visible from every orbit angle.
        self.segments.append((a,b))
        delta = [b[k] - a[k] for k in range(3)]
        length = math.sqrt(sum(v*v for v in delta)) or 1
        d = [v / length for v in delta]
        ref = [0, 1, 0] if abs(d[1]) < .9 else [1, 0, 0]
        u = [d[1]*ref[2]-d[2]*ref[1], d[2]*ref[0]-d[0]*ref[2], d[0]*ref[1]-d[1]*ref[0]]
        norm = math.sqrt(sum(v*v for v in u))
        u = [v/norm for v in u]
        v = [d[1]*u[2]-d[2]*u[1], d[2]*u[0]-d[0]*u[2], d[0]*u[1]-d[1]*u[0]]
        offset = len(self.p)
        for center in [a, b]:
            for j in range(6):
                angle = j * math.pi / 3
                self.p.append([center[k] + .008*(u[k]*math.cos(angle)+v[k]*math.sin(angle)) for k in range(3)])
                self.c.append([*color, 255])
        for j in range(6):
            k = (j+1) % 6
            self.i.extend([offset+j, offset+k, offset+j+6, offset+k, offset+k+6, offset+j+6])

    def cloud(self, center, radius, color, opacity=30):
        # Three intersecting soft radial sheets form a cloud volume with no hard edges.
        self.fog.append((center,radius,color,opacity))
        rng = random.Random(str(center)+str(radius))
        for axis in range(3):
            yaw, tilt = rng.uniform(0,math.tau), rng.uniform(0,math.tau)
            offset = len(self.p)
            self.p.append(center)
            self.c.append([*color, opacity])
            for j in range(25):
                angle = j * math.pi / 12
                x,y = radius*math.cos(angle),radius*math.sin(angle)
                p = [center[0]+x*math.cos(yaw)-y*math.sin(yaw)*math.cos(tilt),
                     center[1]+x*math.sin(yaw)+y*math.cos(yaw)*math.cos(tilt),
                     center[2]+y*math.sin(tilt)]
                self.p.append(p)
                self.c.append([*color, 0])
            for j in range(24):
                self.i.extend([offset, offset+j+1, offset+j+2])

    def save(self, name, title, transparent=False):
        assets.glb(name + '.glb', self.p, self.i, self.c, transparent=transparent,
                   texture=getattr(self,'texture',None),uvs=getattr(self,'uvs',None))
        # Vector preview generated from the same scene, not a borrowed photograph.
        points = self.dots or [(p[0], p[1], .025, c) for p, c in zip(self.p[::18], self.c[::18])]
        span = max(max(abs(p[k]) for p in self.p) for k in [0, 1]) + .3
        circles = ''.join(f'<circle cx="{200+x/span*170:.2f}" cy="{150-y/span*125:.2f}" r="{max(.6,r/span*170):.2f}" fill="rgb{tuple(c[:3])}"/>' for x,y,r,c in points)
        gradients = ''.join(f'<radialGradient id="c{i}"><stop stop-color="rgb{tuple(c)}" stop-opacity="{min(.9,opacity/65):.2f}"/><stop offset="1" stop-color="rgb{tuple(c)}" stop-opacity="0"/></radialGradient>' for i,(_,_,c,opacity) in enumerate(self.fog))
        clouds = ''.join(f'<circle cx="{200+p[0]/span*170:.2f}" cy="{150-p[1]/span*125:.2f}" r="{r/span*170:.2f}" fill="url(#c{i})"/>' for i,(p,r,_,_) in enumerate(self.fog))
        lines = ''.join(f'<path d="M{200+a[0]/span*170:.2f},{150-a[1]/span*125:.2f} L{200+b[0]/span*170:.2f},{150-b[1]/span*125:.2f}" stroke="#689acb" stroke-width=".8"/>' for a,b in self.segments)
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><title>{html.escape(title)} — educational illustration</title><defs><radialGradient id="bg"><stop stop-color="#233453"/><stop offset="1" stop-color="#060b17"/></radialGradient>{gradients}</defs><path fill="url(#bg)" d="M0 0h400v300H0z"/>{clouds}{lines}{circles}</svg>'
        (OUT / (name + '.svg')).write_text(svg, encoding='utf-8')


entries = []


def entry(id, name, category, subtitle, description, position=None, **extra):
    row = dict(id=id, name=name, category=category, subtitle=subtitle, description=description,
               model=id+'.glb', image=id+'.svg', imageAlt=f'Educational illustration of {name}',
               imageCaption='Original educational illustration · enhanced colors, not an eyepiece view',
               modelCredit='Pleiades educational geometry; catalog data: d3-celestial / Olaf Frohn and HYG / David Nash. See atlas credits.',
               modelNote='Educational model: colors and sizes are enhanced; depth is schematic. This is not a measured 3D reconstruction or a live surface view.',
               source='https://github.com/ofrohn/d3-celestial', sourceLabel='Catalog data and credits',
               cameraOrbit='0deg 75deg 110%', observingTip='Dark skies and appropriate equipment matter. Colors and faint detail are enhanced compared with visual observing.')
    if position:
        row['catalogPosition'] = dict(raHours=(position[0] % 360)/15, decDeg=position[1])
    row.update(extra)
    entries.append(row)


# All seven other planets and the Moon. The existing NASA gas giant models remain.
planet_colors = {'mercury': (155,145,132), 'venus': (233,198,138), 'mars': (207,105,64),
                 'uranus': (135,221,226), 'neptune': (63,110,218), 'moon': (185,183,176)}
for id, color in planet_colors.items():
    rng = random.Random(id)
    craters = [(rng.uniform(-math.pi, math.pi), rng.uniform(.15, math.pi-.15), rng.uniform(.025,.17)) for _ in range(95)]
    scene = Scene()
    if id == 'moon':
        scene.texture = moon_texture
        scene.uvs = []
    rows, cols = 96, 192
    for j in range(rows+1):
        t = math.pi*j/rows
        for k in range(cols+1):
            a = 2*math.pi*k/cols
            x,y,z = math.sin(t)*math.cos(a), math.cos(t), math.sin(t)*math.sin(a)
            noise = .035*math.sin(a*33+math.sin(t*15)*3)*math.sin(t*41)+.025*math.sin(a*71+t*53)
            shade = .83 + noise
            radius = 1
            if id in ('moon','mercury','mars'):
                shade += .08*math.sin(a*5+t*8)+.065*math.cos(a*11-t*7)
                for ca,ct,cr in craters:
                    da = (a-ca+math.pi) % (2*math.pi)-math.pi
                    dist = math.hypot(da*math.sin(t), t-ct)/cr
                    if dist < 1.25:
                        shade += .16*math.exp(-((dist-1)*8)**2)-.19*math.exp(-(dist*1.5)**2)
                        radius += -.009*math.exp(-(dist*1.7)**2)+.004*math.exp(-((dist-1)*8)**2)
            else:
                shade += .07*math.sin(t*38+math.sin(a*5)*.4)+.03*math.cos(t*71+a*3)
            light = .35+.65*max(0, x*.35+y*.2+z*.75)
            if id == 'moon':
                scene.uvs.append([k/cols,j/rows])
                radius = 1
                shade = 1
            scene.p.append([x*radius,y*radius,z*radius])
            scene.c.append([min(255,max(0,int(v*shade*light))) for v in ((255,255,255) if id == 'moon' else color)]+[255])
    for j in range(rows):
        for k in range(cols):
            a = j*(cols+1)+k
            scene.i.extend([a,a+cols+1,a+1,a+1,a+cols+1,a+cols+2])
    scene.save(id, id.title())
    category = 'Moon' if id == 'moon' else 'Planet'
    descriptions = {'moon':'Explore cratered highlands, darker maria-like regions, and raised crater rims on our natural satellite.',
                    'mercury':'A small rocky world with a heavily cratered surface.', 'venus':'A rocky world hidden beneath a thick atmosphere and bright cloud cover.',
                    'mars':'The red planet, with an illustrative rocky surface and crater relief.', 'uranus':'An ice giant with a pale cyan atmosphere.',
                    'neptune':'A distant ice giant with blue atmospheric bands.'}
    entry(id,id.title() if id != 'moon' else 'Moon',category,descriptions[id],descriptions[id],
          source=f'https://science.nasa.gov/{"moon" if id == "moon" else id}/', sourceLabel='NASA · '+id.title(),
          modelCredit='Original procedural surface and geometry: Pleiades · CC BY 4.0; not NASA surface imagery.',
          observingTip='Never point binoculars or a telescope near the Sun. Mercury and Venus require special care in twilight.' if id in ('mercury','venus') else 'A telescope reveals more detail; Uranus and Neptune require optical aid. The Moon can be explored with binoculars.')
    if id == 'moon':
        entries[-1].update(image='moon-color.jpg',imageAlt='Lunar surface color map from NASA Lunar Reconnaissance Orbiter',
            imageCaption='LROC global surface map · NASA / GSFC / Arizona State University · Ernie Wright',
            modelCredit='Surface map: NASA Scientific Visualization Studio CGI Moon Kit / LRO / LROC. Sphere geometry: Pleiades.',
            modelNote='Real LRO surface imagery mapped to a sphere. Lighting, rotation and orientation are educational, not the selected lunar phase.',
            source='https://svs.gsfc.nasa.gov/4720/',sourceLabel='NASA · CGI Moon Kit',
            description='Explore the lunar maria, highlands and crater patterns using a real Lunar Reconnaissance Orbiter surface mosaic. The globe is an educational close-up, not the selected lunar phase.')


hyg_url = 'https://raw.githubusercontent.com/astronexus/HYG-Database/main/hyg/CURRENT/hygdata_v40.csv.gz'
hyg = list(csv.DictReader(io.StringIO(gzip.decompress(assets.fetch(hyg_url,CACHE/'hygdata_v40.csv.gz')).decode())))
stars = [r for r in hyg if r['ra'] and r['dec'] and r['mag'] and r['proper']]


def stellar_color(row):
    ci = float(row.get('ci') or .3)
    return (165,200,255) if ci < .15 else (240,241,255) if ci < .6 else (255,219,157) if ci < 1.1 else (255,155,99)


def star_scene(id, name, color):
    scene = Scene()
    p,i,c = assets.sphere()
    scene.p,scene.i = p,i
    scene.c = [[int(color[k]*(.85+.1*math.sin(v[0]*48+v[1]*36)*math.cos(v[2]*42))) for k in range(3)]+[255] for v in p]
    for scale,opacity in [(1.13,40),(1.3,18),(1.6,8)]:
        scene.cloud([0,0,0],scale,color,opacity)
    scene.save(id,name,True)


for star in stars:
    if float(star['mag']) > 2.5 or float(star['dec']) <= -48 or star['proper'] in ('Vega','Sol'):
        continue
    name = star['proper']
    id = 'star-'+name.lower().replace(' ','-')
    star_scene(id,name,stellar_color(star))
    entry(id,name,'Star',f'Bright star in {star["con"]} · magnitude {float(star["mag"]):.1f}',
          f'{name} is a cataloged bright star in {star["con"]}. Its enlarged surface and glow illustrate its stellar color; stars remain points of light through ordinary visual observing.',
          [float(star['ra'])*15,float(star['dec'])], source='https://github.com/astronexus/HYG-Database',sourceLabel='HYG star catalog',
          modelCredit='HYG v4.0: David Nash / Astronexus · CC BY-SA 4.0. Enlarged stellar illustration: Pleiades.')
star_scene('vega-illustration','Vega',(165,200,255))


# Include any IAU region that rises at some point from WNY's southern edge (42 N).
# Some of these only show a small northern portion; the full figure stays explorable.
names = {f['id']:f for f in data('constellations.json')}
bounds = {}
for f in data('constellations.bounds.json'):
    key = f['id'][:3]
    coords = f['geometry']['coordinates']
    def flatten(value):
        if isinstance(value[0], (float,int)):
            yield value
        else:
            for child in value:
                yield from flatten(child)
    bounds.setdefault(key,[]).extend(flatten(coords))
patterns = {}
for f in data('constellations.lines.json'):
    patterns.setdefault(f['id'][:3],[]).extend(f['geometry']['coordinates'])
for code, feature in names.items():
    boundary = bounds.get(code,[])
    if not boundary or max(p[1] for p in boundary) <= -48:
        continue
    paths = patterns.get(code,[])
    points = list({tuple(p) for path in paths for p in path})
    center = feature['geometry']['coordinates']
    # Local tangent view on a sphere: angular layout preserved, no invented stellar distances.
    ra0 = math.atan2(sum(math.sin(math.radians(p[0])) for p in points),sum(math.cos(math.radians(p[0])) for p in points)) if points else math.radians(center[0])
    dec0 = math.radians(sum(p[1] for p in points)/len(points)) if points else math.radians(center[1])
    def project(p):
        a,d = math.radians(p[0])-ra0, math.radians(p[1])
        return [-math.cos(d)*math.sin(a)*6,(math.sin(d)*math.cos(dec0)-math.cos(d)*math.cos(a)*math.sin(dec0))*6,
                (math.sin(d)*math.sin(dec0)+math.cos(d)*math.cos(a)*math.cos(dec0)-1)*6]
    scene = Scene()
    labels = []
    for p in points:
        xyz = project(p)
        nearest = min(stars,key=lambda r: (((float(r['ra'])*15-p[0]+180)%360-180)*math.cos(math.radians(p[1])))**2+(float(r['dec'])-p[1])**2)
        dist = math.hypot(((float(nearest['ra'])*15-p[0]+180)%360-180)*math.cos(math.radians(p[1])),float(nearest['dec'])-p[1])
        mag = float(nearest['mag']) if dist < .08 else 4
        scene.ball(xyz,.025+max(0,5-mag)*.009,stellar_color(nearest) if dist < .08 else (205,220,255))
        if dist < .08:
            labels.append(dict(name=nearest['proper'],position=xyz))
    for path in paths:
        for a,b in zip(path,path[1:]):
            scene.line(project(a),project(b))
    # Place cataloged nebulae in their constellation figure as well as standalone views.
    def inside(point):
        unwrap = lambda value: (value-math.degrees(ra0)+180)%360-180
        x,y = unwrap(point[0]),point[1]
        vertices = [(unwrap(p[0]),p[1]) for p in boundary]
        result = False
        for (ax,ay),(bx,by) in zip(vertices,vertices[1:]+vertices[:1]):
            if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
                result = not result
        return result
    has_cloud = False
    for nebula in data('messier.json'):
        if nebula['properties']['type'] not in ('sfr','pn','snr','rn') and nebula['id'] != 'M45':
            continue
        coord = nebula['geometry']['coordinates']
        if not inside(coord):
            continue
        xyz = project(coord)
        color = (75,145,255) if nebula['id'] == 'M45' else (210,100,202)
        for offset in [-.035,0,.035]:
            scene.cloud([xyz[0]+offset,xyz[1],xyz[2]],.09,color,55)
        labels.insert(0,dict(name=nebula['properties']['alt'] or nebula['id'],position=xyz))
        has_cloud = True
    if not points:
        scene.ball([0,0,0],.1,(200,220,255))
    name = feature['properties']['name']
    id = 'constellation-'+code.lower()
    scene.save(id,name,has_cloud)
    partial = min(p[1] for p in boundary) < -46.6
    entry(id,name,'Constellation',('Partially visible / low southern horizon' if partial else 'Seasonal constellation visible from WNY'),
          f'{name} is an IAU constellation. The connecting lines show a traditional figure, not physical connections between stars. '+('Only its northern portion rises from parts of WNY; the full figure is shown for learning.' if partial else 'Its position in the night sky changes with season and time.'),
          center, labels=labels[:14], partialFromWny=partial, cameraOrbit='0deg 90deg 115%',
          modelNote='J2000 angular star pattern on a spherical sky shell, with enlarged stars and optional labels. Depth is sky curvature, not measured stellar distance. Lines illustrate a figure, not IAU boundaries.')


def deep_scene(id, title, kind, seed, reflection=False, morphology='s'):
    rng = random.Random(seed)
    scene = Scene()
    if kind == 'Galaxy':
        for i in range(2400):
            radius = rng.random()**.65*3.6
            angle = (i%2)*math.pi+radius*1.9+rng.gauss(0,.17)
            xyz = [radius*math.cos(angle),rng.gauss(0,.045+.16*math.exp(-radius*2)),radius*math.sin(angle)*.68]
            color = (255,222,168) if radius < 1 else (155,193,255)
            if morphology in ('e', 'i'):
                xyz = [rng.gauss(0,1.15),rng.gauss(0,.65),rng.gauss(0,.8)]
                color = (255,218,170)
            scene.ball(xyz,rng.uniform(.009,.027),color)
        for i in range(50 if morphology == 's' else 0):
            r = rng.random()*3.5
            a = (i%2)*math.pi+r*1.9
            scene.cloud([r*math.cos(a),0,r*math.sin(a)*.68],.3,(100,131,235),15)
        scene.cloud([0,0,0],.9,(255,202,135),95)
    elif kind == 'Nebula':
        ring = seed in ('M57','M97')
        for i in range(180):
            a = rng.random()*math.tau
            r = rng.gauss(1.4,.16) if ring else rng.random()**.6*2.5
            xyz = [r*math.cos(a),r*math.sin(a)*.72,rng.gauss(0,.38)]
            color = (95,165,255) if reflection else [(247,80,149),(112,111,245),(69,208,217)][i%3]
            scene.cloud(xyz,rng.uniform(.25,.75),color,rng.randint(14,42))
        for i in range(70):
            scene.ball([rng.uniform(-3,3),rng.uniform(-2,2),rng.uniform(-.5,.5)],rng.uniform(.01,.035),(205,225,255))
    else:
        globular = seed.startswith('M') and seed in GLOBULAR
        count = 2 if seed == 'M40' else 4 if seed == 'M73' else 1300 if globular else 230
        for i in range(count):
            r = rng.random()**(1.7 if globular else .5)*2.6
            a = rng.random()*math.tau
            v = rng.uniform(-1,1)
            xyz = [r*math.sqrt(1-v*v)*math.cos(a),r*v,r*math.sqrt(1-v*v)*math.sin(a)]
            scene.ball(xyz,rng.uniform(.012,.04),rng.choice([(183,210,255),(255,223,170),(235,242,255)]))
        if reflection:
            for _ in range(80):
                scene.cloud([rng.gauss(0,1),rng.gauss(0,.8),rng.gauss(0,.5)],rng.uniform(.3,1),(80,145,255),22)
    scene.save(id,title,True)


messier = data('messier.json')
GLOBULAR = {f['id'] for f in messier if f['properties']['type']=='gc'}
for f in messier:
    p = f['properties']
    if f['id'] in ('M31','M45') or f['geometry']['coordinates'][1] <= -48:
        continue
    kind = 'Galaxy' if p['type'] in ('s','e','i','g','s0') else 'Nebula' if p['type'] in ('sfr','pn','snr','bn','dn','rn') else 'Star field' if p['type'] == 'pos' else 'Star cluster'
    id = f['id'].lower()
    title = p['alt'] or f['id']
    if title != f['id']:
        title += ' ('+f['id']+')'
    deep_scene(id,title,kind,f['id'],morphology=p['type'])
    entry(id,title,kind,f'{f["id"]} · {p["desig"] or "deep-sky field"} · magnitude {p["mag"]}',
          f'{title} is a {kind.lower()} target in the Messier catalog. This detailed illustration shows '+('an enhanced-color gas and dust cloud with embedded stars.' if kind=='Nebula' else 'its general structure with many individual stellar points. Individual stars and depth are illustrative.'),
          f['geometry']['coordinates'], cameraOrbit='0deg 45deg 110%' if kind=='Galaxy' else '0deg 80deg 110%')
deep_scene('andromeda-illustration','Andromeda Galaxy','Galaxy','M31')
# Preserve the measured angular Pleiades star layout, adding blue reflection clouds.
cluster = Scene()
named = json.loads((ROOT/'src/explore/star-catalog.json').read_text())['stars']
named = [s for s in named if s['name'] != 'Vega']
mean_ra = sum(s['ra_hours'] for s in named)/len(named)
mean_dec = sum(s['dec_deg'] for s in named)/len(named)
rng = random.Random(45)
for s in named:
    xyz = [-(s['ra_hours']-mean_ra)*15*math.cos(math.radians(mean_dec))*2,(s['dec_deg']-mean_dec)*2,0]
    cluster.ball(xyz,.04+max(0,6-s['magnitude'])*.025,(190,217,255))
    for _ in range(12):
        cluster.cloud([xyz[0]+rng.gauss(0,.35),xyz[1]+rng.gauss(0,.3),rng.gauss(0,.3)],rng.uniform(.3,.7),(75,142,255),24)
cluster.save('pleiades','Pleiades',True)
entries.sort(key=lambda r:(r['category'],r['name']))
(ROOT/'src/explore/expanded-catalog.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'atlas-credits.json').write_text(json.dumps(dict(sources=[DATA_URL,hyg_url,moon_texture_url,'https://svs.gsfc.nasa.gov/4720/'],
    selection='Constellations whose J2000 boundary reaches declination > -48 degrees; bright named HYG stars (V <= 2.5, dec > -48); all Messier objects above -48; seven other planets and Moon.',
    licenses=['d3-celestial: BSD-3-Clause; see d3-celestial-LICENSE.txt','HYG: CC BY-SA 4.0; derived constellation/star layouts retain attribution','Original models: CC BY 4.0; catalog-derived layouts: CC BY-SA 4.0'],
    geometry='Enhanced educational illustrations, not measured 3D reconstructions. Moon: NASA SVS LRO/LROC real surface mosaic; other new planetary surfaces procedural. Existing Jupiter/Saturn NASA models retained.'),indent=2)+'\n')
print(f'Built {len(entries)} additional entries, plus upgraded Vega, Pleiades and Andromeda.')
