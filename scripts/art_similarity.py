"""Deterministic coarse SVG duplicate-review signatures, not browser rendering.

Only the renderer's closed vocabulary is accepted. Curves are flattened, fills
use nonzero winding and strokes use sampled segment coverage (round joins).
There is no antialiasing; tiny details may disappear at the default 80x50 grid.
"""
from __future__ import annotations

import base64
from functools import lru_cache
import math
import re
import xml.etree.ElementTree as ET
import zlib

RASTERIZER_VERSION = "coarse-svg-rgb-1"
WIDTH, HEIGHT = 80, 50
NEAR_TWIN_LIMITS = {"full_mean_difference": 0.025,
                    "foreground_mean_difference": 0.08, "foreground_iou": 0.84}
BACKGROUND = PAPER = (244, 240, 232)
_NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"
_TOKEN = re.compile(r"[A-Za-z]|" + _NUMBER)
IDENTITY = (1., 0., 0., 1., 0., 0.)


def _numbers(text):
    if re.sub(_NUMBER, '', text).strip(' ,\t\r\n'):
        raise ValueError('Unsupported SVG numeric syntax')
    result = [float(n) for n in re.findall(_NUMBER, text)]
    if any(not math.isfinite(n) or abs(n) > 1e7 for n in result):
        raise ValueError('SVG coordinate out of bounds')
    return result


def _mul(a, b):
    return (a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
            a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
            a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5])


def _point(m, p):
    return (m[0]*p[0]+m[2]*p[1]+m[4], m[1]*p[0]+m[3]*p[1]+m[5])


def _transform(text):
    out = IDENTITY
    pattern = r'([A-Za-z]+)\s*\(([^()]*)\)'
    if re.sub(pattern, '', text).strip(' ,\t\n'):
        raise ValueError('Unsupported SVG transform')
    for name, args in re.findall(pattern, text):
        n = _numbers(args)
        if name == 'translate' and len(n) in (1, 2):
            m = (1, 0, 0, 1, n[0], n[1] if len(n) == 2 else 0)
        elif name == 'scale' and len(n) in (1, 2) and (len(n) == 1 or n[0] == n[1]):
            m = (n[0], 0, 0, n[0], 0, 0)
        elif name == 'rotate' and len(n) in (1, 3):
            c, s = math.cos(math.radians(n[0])), math.sin(math.radians(n[0]))
            m = (c, s, -s, c, 0, 0)
            if len(n) == 3:
                m = _mul(_mul((1,0,0,1,n[1],n[2]), m), (1,0,0,1,-n[1],-n[2]))
        else:
            raise ValueError('Unsupported SVG transform: ' + name)
        out = _mul(out, m)
    return out


def _paths(d):
    if _TOKEN.sub('', d).strip(' ,\t\r\n'):
        raise ValueError('Unsupported SVG path syntax')
    tokens = _TOKEN.findall(d)
    result, points = [], []
    pos, start, cmd, i = (0., 0.), (0., 0.), None, 0
    sizes = {'M':2, 'L':2, 'H':1, 'V':1, 'Q':4, 'C':6}
    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]; i += 1
            if cmd.upper() == 'Z':
                if not points:
                    raise ValueError('SVG close without subpath')
                points.append(start); result.append((points, True)); points = []
                pos = start; cmd = None
                continue
        if cmd is None or cmd.upper() not in sizes:
            raise ValueError('Unsupported SVG path command: ' + str(cmd))
        op, count = cmd.upper(), sizes[cmd.upper()]
        if i+count > len(tokens) or any(t.isalpha() for t in tokens[i:i+count]):
            raise ValueError('Incomplete SVG path command')
        n = _numbers(' '.join(tokens[i:i+count])); i += count
        relative = cmd.islower()
        def pair(k):
            return (n[k]+(pos[0] if relative else 0), n[k+1]+(pos[1] if relative else 0))
        if op == 'M':
            if points: result.append((points, False))
            pos = pair(0); start = pos; points = [pos]
            cmd = 'l' if relative else 'L'
        else:
            if not points: points = [pos]
            if op == 'H': end = (n[0]+(pos[0] if relative else 0), pos[1])
            elif op == 'V': end = (pos[0], n[0]+(pos[1] if relative else 0))
            else: end = pair(count-2)
            if op in ('Q', 'C'):
                controls = [pos, pair(0)] + ([pair(2)] if op == 'C' else []) + [end]
                for step in range(1, 17):
                    t = step/16
                    work = controls[:]
                    while len(work) > 1:
                        work = [((1-t)*a[0]+t*b[0], (1-t)*a[1]+t*b[1]) for a,b in zip(work,work[1:])]
                    points.append(work[0])
            else: points.append(end)
            pos = end
    if points: result.append((points, False))
    return result


def _color(value):
    if value == 'none': return None
    if re.fullmatch(r'#[0-9a-fA-F]{3}', value):
        value = '#' + ''.join(c*2 for c in value[1:])
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Unsupported SVG color: ' + value)
    return tuple(int(value[i:i+2],16) for i in (1,3,5))


def rasterize(svg: bytes, width=WIDTH, height=HEIGHT) -> bytes:
    """Return packed RGB, letterboxed to preserve the SVG viewBox aspect ratio."""
    if not (isinstance(width, int) and isinstance(height, int) and 1 <= width <= 512 and 1 <= height <= 512):
        raise ValueError('Raster dimensions must be integers from 1 to 512')
    return _rasterize_cached(bytes(svg), width, height)


@lru_cache(maxsize=256)
def _rasterize_cached(svg: bytes, width: int, height: int) -> bytes:
    """Cache immutable output only; public entry point validates every call."""
    if len(svg) > 2_000_000 or b'<!' in svg:
        raise ValueError('SVG declarations or oversized input are unsupported')
    try: root = ET.fromstring(svg)
    except ET.ParseError as exc: raise ValueError('Invalid SVG') from exc
    if root.tag.split('}')[-1] != 'svg': raise ValueError('Expected SVG root')
    vb = _numbers(root.get('viewBox', '0 0 '+root.get('width','1200')+' '+root.get('height','760')))
    if len(vb) != 4 or vb[2] <= 0 or vb[3] <= 0: raise ValueError('Invalid SVG viewBox')
    scale = min(width/vb[2], height/vb[3])
    initial = (scale,0,0,scale,(width-vb[2]*scale)/2-vb[0]*scale,(height-vb[3]*scale)/2-vb[1]*scale)
    pixels = bytearray(PAPER * (width*height))
    def paint(mask, color, alpha):
        if color is None or alpha == 0: return
        for index in mask:
            offset = index*3
            for channel in range(3):
                pixels[offset+channel] = round(pixels[offset+channel]*(1-alpha)+color[channel]*alpha)
    style_keys = {'fill','stroke','fill-opacity','stroke-opacity','stroke-width','stroke-linecap','stroke-linejoin','stroke-dasharray','fill-rule'}
    geometry = {'svg':{'viewBox','width','height','role','aria-label'}, 'g':set(),
                'path':{'d'}, 'rect':{'x','y','width','height','rx','ry'}, 'circle':{'cx','cy','r'}}
    def visit(node, transform, inherited):
        tag = node.tag.split('}')[-1]
        if node.tag not in (tag, '{http://www.w3.org/2000/svg}' + tag):
            raise ValueError('Unsupported SVG namespace')
        if tag in ('title','desc'):
            if list(node) or node.attrib: raise ValueError('Unsupported SVG metadata')
            return
        if tag not in geometry: raise ValueError('Unsupported SVG element: '+tag)
        if node is not root and tag == 'svg': raise ValueError('Nested SVG unsupported')
        for key in node.attrib:
            if key not in geometry[tag] | style_keys | {'transform','id'}:
                raise ValueError('Unsupported SVG attribute: '+key)
        style = dict(inherited); style.update({k:v for k,v in node.attrib.items() if k in style_keys})
        if style.get('fill-rule','nonzero') != 'nonzero': raise ValueError('Only nonzero fill is supported')
        if style.get('stroke-linecap','butt') not in ('round','butt','square'): raise ValueError('Unsupported stroke cap')
        if style.get('stroke-linejoin','miter') not in ('round','miter','bevel'): raise ValueError('Unsupported stroke join')
        m = _mul(transform, _transform(node.get('transform','')))
        if tag in ('svg','g'):
            for child in node: visit(child,m,style)
            return
        if list(node): raise ValueError('SVG shapes cannot contain children')
        def num(key, default='0'):
            n = _numbers(node.get(key,default))
            if len(n) != 1: raise ValueError('Expected one SVG number')
            return n[0]
        if tag == 'path': paths = _paths(node.get('d',''))
        elif tag == 'circle':
            x,y,r = num('cx'),num('cy'),num('r')
            if r < 0: raise ValueError('Negative circle radius')
            p = [(x+r*math.cos(i*math.tau/64),y+r*math.sin(i*math.tau/64)) for i in range(65)]
            paths = [(p,True)]
        else:
            x,y,w,h = num('x'),num('y'),num('width'),num('height')
            rx,ry = num('rx',node.get('ry','0')),num('ry',node.get('rx','0'))
            if min(w,h,rx,ry)<0: raise ValueError('Negative rectangle dimension')
            rx,ry = min(rx,w/2),min(ry,h/2)
            p = []
            for cx,cy,angle in ((x+w-rx,y+ry,-90),(x+w-rx,y+h-ry,0),(x+rx,y+h-ry,90),(x+rx,y+ry,180)):
                p.extend((cx+rx*math.cos(math.radians(angle+i*90/8)),cy+ry*math.sin(math.radians(angle+i*90/8))) for i in range(9))
            paths = [(p+[p[0]],True)]
        paths = [([_point(m,p) for p in points],closed) for points,closed in paths]
        fill,stroke = _color(style.get('fill','#000000')), _color(style.get('stroke','none'))
        def opacity(key):
            n = _numbers(style.get(key,'1'))
            if len(n)!=1 or not 0<=n[0]<=1: raise ValueError('Invalid SVG opacity')
            return n[0]
        if fill is not None:
            edges = [(a,b) for points,_ in paths for a,b in zip(points,points[1:]+points[:1]) if a[1]!=b[1]]
            mask = set()
            for y in range(height):
                sy = y+.5
                hits = sorted((a[0]+(sy-a[1])*(b[0]-a[0])/(b[1]-a[1]),1 if b[1]>a[1] else -1) for a,b in edges if min(a[1],b[1])<=sy<max(a[1],b[1]))
                winding, previous = 0, 0
                for x,delta in hits:
                    if winding:
                        mask.update(y*width+px for px in range(max(0,math.ceil(previous-.5)),min(width,math.ceil(x-.5))))
                    winding += delta; previous = x
            paint(mask,fill,opacity('fill-opacity'))
        if stroke is not None:
            ns = _numbers(style.get('stroke-width','1'))
            if len(ns)!=1 or ns[0]<0: raise ValueError('Invalid stroke width')
            factor = math.hypot(m[0],m[1]); radius = ns[0]*factor/2
            dash_text = style.get('stroke-dasharray','none')
            dash = [] if dash_text == 'none' else _numbers(dash_text)
            if dash_text != 'none' and (not dash or min(dash)<=0): raise ValueError('Unsupported dash array')
            if len(dash)%2: dash *= 2
            dash = [v*factor for v in dash]
            mask = set()
            for points,closed in paths:
                segments = []; di, remaining = 0, dash[0] if dash else 0
                for a,b in zip(points,points[1:]):
                    length = math.dist(a,b)
                    if not length: continue
                    if not dash: segments.append((a,b)); continue
                    used = 0
                    while used < length-1e-10:
                        take = min(remaining,length-used)
                        if di%2 == 0:
                            segments.append(((a[0]+(b[0]-a[0])*used/length,a[1]+(b[1]-a[1])*used/length),(a[0]+(b[0]-a[0])*(used+take)/length,a[1]+(b[1]-a[1])*(used+take)/length)))
                        used += take; remaining -= take
                        if remaining < 1e-10:
                            di=(di+1)%len(dash); remaining=dash[di]
                for a,b in segments:
                    dx,dy=b[0]-a[0],b[1]-a[1]; squared=dx*dx+dy*dy
                    for y in range(max(0,math.floor(min(a[1],b[1])-radius)),min(height,math.ceil(max(a[1],b[1])+radius))):
                        for x in range(max(0,math.floor(min(a[0],b[0])-radius)),min(width,math.ceil(max(a[0],b[0])+radius))):
                            t=((x+.5-a[0])*dx+(y+.5-a[1])*dy)/squared
                            cap=style.get('stroke-linecap','butt')
                            if not closed and cap=='butt' and (t<0 or t>1): continue
                            if cap=='square': t=max(-radius/math.sqrt(squared),min(1+radius/math.sqrt(squared),t))
                            else: t=max(0,min(1,t))
                            if (x+.5-a[0]-t*dx)**2+(y+.5-a[1]-t*dy)**2<=radius*radius:
                                mask.add(y*width+x)
            paint(mask,stroke,opacity('stroke-opacity'))
    visit(root,initial,{})
    return bytes(pixels)


def encode_signature(pixels: bytes) -> str:
    if not pixels or len(pixels)%3 or len(pixels)>512*512*3:
        raise ValueError('Expected bounded packed RGB pixels')
    return 'rgb1:' + base64.b64encode(zlib.compress(pixels,9)).decode('ascii')


def decode_signature(signature: str) -> bytes:
    if not signature.startswith('rgb1:'): raise ValueError('Unsupported raster signature')
    try:
        compressed = base64.b64decode(signature[5:],validate=True)
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(compressed,512*512*3+1)
        if not decoder.eof or decoder.unused_data or len(pixels)>512*512*3:
            raise ValueError('Invalid or oversized raster signature')
    except (ValueError,zlib.error) as exc: raise ValueError('Invalid raster signature') from exc
    if not pixels or len(pixels)%3: raise ValueError('Invalid RGB raster signature')
    return pixels


def compare(left: bytes, right: bytes) -> dict:
    """RGB mean absolute errors and foreground IoU against fixed paper color.

    Foreground difference averages the union of both foreground masks, so
    unchanged paper padding cannot conceal a changed principal object.
    """
    if not left or len(left)!=len(right) or len(left)%3:
        raise ValueError('Expected equal nonempty packed RGB rasters')
    left, right = bytes(left), bytes(right)
    if right < left:
        left, right = right, left
    values = _compare_cached(left, right)
    return dict(zip(('full_mean_difference', 'foreground_mean_difference',
                     'foreground_iou', 'foreground_pixels'), values))


@lru_cache(maxsize=8192)
def _compare_cached(left: bytes, right: bytes) -> tuple:
    # Never cache a mutable dictionary exposed to callers.
    total,foreground,union,intersection = 0,0,0,0
    for i in range(0,len(left),3):
        ar, ag, ab = left[i], left[i+1], left[i+2]
        br, bg, bb = right[i], right[i+1], right[i+2]
        delta = abs(ar-br)+abs(ag-bg)+abs(ab-bb); total+=delta
        fa = ar!=PAPER[0] or ag!=PAPER[1] or ab!=PAPER[2]
        fb = br!=PAPER[0] or bg!=PAPER[1] or bb!=PAPER[2]
        if fa or fb: union+=1; foreground+=delta
        if fa and fb: intersection+=1
    return (total/(len(left)*255),
            foreground/(union*3*255) if union else 0.,
            intersection/union if union else 1., union)


def is_near_twin(metrics: dict) -> bool:
    """Conservative review trigger, never a guarantee of contextual uniqueness."""
    return (metrics.get('foreground_pixels', 0) > 0
            and metrics['full_mean_difference'] <= NEAR_TWIN_LIMITS['full_mean_difference']
            and metrics['foreground_mean_difference'] <= NEAR_TWIN_LIMITS['foreground_mean_difference']
            and metrics['foreground_iou'] >= NEAR_TWIN_LIMITS['foreground_iou'])
