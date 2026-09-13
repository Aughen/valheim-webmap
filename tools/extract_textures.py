#!/usr/bin/env python3
"""Pull the textures the 3D view needs out of the game's own files. No dependencies.

The mod does this itself on the server now; this tool is the manual fallback
(a client install on another machine, an unusual host, or just checking).
It reads map_data/models/textures.json (the names the exported models want),
finds each one in the game's asset bundles / .assets files, decodes it
(DXT1, DXT5, BC7, raw RGB/RGBA) and writes tex_<name>.png next to the models.
The mod picks new files up within a minute.

    python extract_textures.py <valheim_Data or valheim_server_Data> <map_data/models> [--size 512] [--all] [--names a,b,c]
"""
import argparse, json, os, re, struct, sys, time, zlib

# ------------------------------------------------------------------ UnityFS bundle
def lz4_block(src, dst_size):
    dst = bytearray(dst_size); si = 0; di = 0; n = len(src)
    while si < n:
        tok = src[si]; si += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[si]; si += 1; lit += b
                if b != 255: break
        dst[di:di+lit] = src[si:si+lit]; si += lit; di += lit
        if si >= n: break
        off = src[si] | (src[si+1] << 8); si += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[si]; si += 1; ml += b
                if b != 255: break
        ml += 4
        start = di - off
        if off >= ml: dst[di:di+ml] = dst[start:start+ml]; di += ml
        else:
            for i in range(ml): dst[di] = dst[start+i]; di += 1
    return bytes(dst[:di])

class BE:
    def __init__(s, b, pos=0): s.b = b; s.p = pos
    def u16(s): v = struct.unpack_from('>H', s.b, s.p)[0]; s.p += 2; return v
    def u32(s): v = struct.unpack_from('>I', s.b, s.p)[0]; s.p += 4; return v
    def i64(s): v = struct.unpack_from('>q', s.b, s.p)[0]; s.p += 8; return v
    def cstr(s): e = s.b.index(b'\0', s.p); v = s.b[s.p:e].decode(); s.p = e + 1; return v
    def bytes(s, n): v = s.b[s.p:s.p+n]; s.p += n; return v
    def align(s, a): s.p = (s.p + a - 1) // a * a

def decompress(data, flags, usize):
    c = flags & 0x3F
    if c == 0: return data
    if c in (2, 3): return lz4_block(data, usize)
    raise Exception('LZMA-compressed bundle not supported')

class Bundle:
    """reads blocks on demand so big bundles do not sit in memory"""
    def __init__(self, path):
        self.f = open(path, 'rb'); head = self.f.read(4096)
        r = BE(head); sig = r.cstr()
        if sig != 'UnityFS': raise Exception('not a UnityFS bundle')
        ver = r.u32(); r.cstr(); r.cstr(); r.i64(); cbi = r.u32(); ubi = r.u32(); flags = r.u32()
        if ver >= 7: r.align(16)
        if flags & 0x80:
            self.f.seek(-cbi, 2); bi = self.f.read(cbi); after = r.p
        else:
            self.f.seek(r.p); bi = self.f.read(cbi); after = r.p + cbi
        info = BE(decompress(bi, flags, ubi)); info.bytes(16)
        nb = info.u32(); self.blocks = []; foff = after
        if flags & 0x200: foff = (foff + 15) // 16 * 16
        doff = 0
        for i in range(nb):
            u = info.u32(); c = info.u32(); fl = info.u16(); self.blocks.append((u, c, fl, foff, doff)); foff += c; doff += u
        nn = info.u32(); self.nodes = {}
        for i in range(nn):
            off = info.i64(); sz = info.i64(); info.u32(); name = info.cstr(); self.nodes[name] = (off, sz)
        self.cache = (-1, None)
    def _block(self, i):
        if self.cache[0] == i: return self.cache[1]
        u, c, fl, foff, doff = self.blocks[i]
        self.f.seek(foff); data = decompress(self.f.read(c), fl, u); self.cache = (i, data); return data
    def read(self, off, size):
        out = bytearray(); lo = 0; hi = len(self.blocks) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.blocks[mid][4] <= off: lo = mid
            else: hi = mid - 1
        i = lo
        while len(out) < size and i < len(self.blocks):
            b = self.blocks[i]; start = off + len(out) - b[4]; take = min(size - len(out), b[0] - start)
            out += self._block(i)[start:start+take]; i += 1
        return bytes(out)
    def node(self, name): off, sz = self.nodes[name]; return self.read(off, sz)
    def close(self): self.f.close()

# ------------------------------------------------------------------ serialized file + type tree
COMMON = b"AABB\0AnimationClip\0AnimationCurve\0AnimationState\0Array\0Base\0BitField\0bitset\0bool\0char\0ColorRGBA\0Component\0data\0deque\0double\0dynamic_array\0FastPropertyName\0first\0float\0Font\0GameObject\0Generic Mono\0GradientNEW\0GUID\0GUIStyle\0int\0list\0long long\0map\0Matrix4x4f\0MdFour\0MonoBehaviour\0MonoScript\0m_ByteSize\0m_Curve\0m_EditorClassIdentifier\0m_EditorHideFlags\0m_Enabled\0m_ExtensionPtr\0m_GameObject\0m_Index\0m_IsArray\0m_IsStatic\0m_MetaFlag\0m_Name\0m_ObjectHideFlags\0m_PrefabInternal\0m_PrefabParentObject\0m_Script\0m_StaticEditorFlags\0m_Type\0m_Version\0Object\0pair\0PPtr<Component>\0PPtr<GameObject>\0PPtr<Material>\0PPtr<MonoBehaviour>\0PPtr<MonoScript>\0PPtr<Object>\0PPtr<Prefab>\0PPtr<Sprite>\0PPtr<TextAsset>\0PPtr<Texture>\0PPtr<Texture2D>\0PPtr<Transform>\0Prefab\0Quaternionf\0Rectf\0RectInt\0RectOffset\0second\0set\0short\0size\0SInt16\0SInt32\0SInt64\0SInt8\0staticvector\0string\0TextAsset\0TextMesh\0Texture\0Texture2D\0Transform\0TypelessData\0UInt16\0UInt32\0UInt64\0UInt8\0unsigned int\0unsigned long long\0unsigned short\0vector\0Vector2f\0Vector3f\0Vector4f\0m_ScriptingClassIdentifier\0Gradient\0Type*\0int2_storage\0int3_storage\0BoundsInt\0m_CorrespondingSourceObject\0m_PrefabInstance\0m_PrefabAsset\0FileSize\0Hash128\0RenderingLayerMask\0"

class LE:
    def __init__(s, b, p=0): s.b = b; s.p = p
    def u8(s): v = s.b[s.p]; s.p += 1; return v
    def i16(s): v = struct.unpack_from('<h', s.b, s.p)[0]; s.p += 2; return v
    def u16(s): v = struct.unpack_from('<H', s.b, s.p)[0]; s.p += 2; return v
    def i32(s): v = struct.unpack_from('<i', s.b, s.p)[0]; s.p += 4; return v
    def u32(s): v = struct.unpack_from('<I', s.b, s.p)[0]; s.p += 4; return v
    def i64(s): v = struct.unpack_from('<q', s.b, s.p)[0]; s.p += 8; return v
    def u64(s): v = struct.unpack_from('<Q', s.b, s.p)[0]; s.p += 8; return v
    def f32(s): v = struct.unpack_from('<f', s.b, s.p)[0]; s.p += 4; return v
    def cstr(s): e = s.b.index(b'\0', s.p); v = s.b[s.p:e].decode('utf-8', 'replace'); s.p = e + 1; return v
    def bytes(s, n): v = s.b[s.p:s.p+n]; s.p += n; return v
    def align(s, a=4): s.p = (s.p + a - 1) // a * a

def tt_string(buf, off):
    src = COMMON if off & 0x80000000 else buf; off &= 0x7fffffff
    e = src.index(b'\0', off); return src[off:e].decode()

class Node: pass

def looks_serialized(d):
    if len(d) < 48: return False
    ver = struct.unpack_from('>I', d, 8)[0]; return 5 <= ver <= 40

def parse(data):
    ms, fs, ver, do = struct.unpack_from('>IIII', data, 0); p = 16
    endian = data[p]; p += 4
    if ver >= 22: ms, fs, do, _ = struct.unpack_from('>IqqQ', data, p); p += 28
    if endian != 0: raise Exception('big-endian file')
    r = LE(data, p); r.cstr(); r.i32(); ett = r.u8()
    types = []
    for i in range(r.i32()):
        cid = r.i32(); r.u8(); r.i16()
        if cid == 114: r.bytes(16)
        r.bytes(16); nodes = None
        if ett:
            nn = r.i32(); sbs = r.i32(); raw = []
            for j in range(nn):
                n = Node(); r.u16(); n.level = r.u8(); r.u8(); n.type_off = r.u32(); n.name_off = r.u32(); n.size = r.i32(); r.i32(); n.meta = r.i32()
                if ver >= 19: r.u64()
                raw.append(n)
            sbuf = r.bytes(sbs)
            for n in raw: n.type = tt_string(sbuf, n.type_off); n.name = tt_string(sbuf, n.name_off)
            nodes = raw
            if ver >= 21: r.bytes(4 * r.i32())
        types.append((cid, nodes))
    objs = []
    for i in range(r.i32()):
        r.align(4); pid = r.i64(); start = r.i64() if ver >= 22 else r.u32(); size = r.u32(); tidx = r.i32()
        objs.append((pid, do + start, size, tidx))
    return types, objs

PRIM = {'int', 'SInt32', 'unsigned int', 'UInt32', 'SInt64', 'UInt64', 'long long', 'unsigned long long', 'float', 'bool', 'UInt8', 'char', 'SInt8', 'SInt16', 'UInt16', 'short', 'unsigned short', 'FileSize'}
def read_value(r, nodes, i):
    n = nodes[i]; t = n.type; align = (n.meta & 0x4000) != 0
    j = i + 1
    while j < len(nodes) and nodes[j].level > n.level: j += 1
    if t == 'string':
        ln = r.i32(); v = r.bytes(ln).decode('utf-8', 'replace'); r.align(4); return v, j
    if t == 'TypelessData':
        ln = r.i32(); v = r.bytes(ln)
        if align: r.align(4)
        return v, j
    if j > i + 1 and nodes[i+1].type == 'Array':
        arr = nodes[i+1]; ln = r.i32(); elem = i + 3; et = nodes[elem].type
        if et in ('UInt8', 'char') and elem + 1 >= j: v = r.bytes(ln)
        else:
            v = []
            for k in range(ln): val, _ = read_value(r, nodes, elem); v.append(val)
        if (arr.meta & 0x4000) or align: r.align(4)
        return v, j
    if j == i + 1:
        f = {'int': r.i32, 'SInt32': r.i32, 'unsigned int': r.u32, 'UInt32': r.u32, 'SInt64': r.i64, 'UInt64': r.u64, 'long long': r.i64, 'unsigned long long': r.u64, 'float': r.f32, 'bool': r.u8, 'UInt8': r.u8, 'char': r.u8, 'SInt8': r.u8, 'SInt16': r.i16, 'UInt16': r.u16, 'short': r.i16, 'unsigned short': r.u16, 'FileSize': r.u64}.get(t)
        v = f() if f else r.bytes(n.size)
        if align: r.align(4)
        return v, j
    d = {}; k = i + 1
    while k < j:
        val, k2 = read_value(r, nodes, k); d[nodes[k].name] = val; k = k2
    if align: r.align(4)
    return d, j

# ------------------------------------------------------------------ texture decoding

def rgb565(v): return ((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31

def dxt1_block(data, p, out, w, h, bx, by, alpha=None, force4=False):
    c0, c1, idx = struct.unpack_from('<HHI', data, p)
    r0, g0, b0 = rgb565(c0); r1, g1, b1 = rgb565(c1)
    if c0 > c1 or force4:
        pal = [(r0, g0, b0, 255), (r1, g1, b1, 255), ((2*r0+r1)//3, (2*g0+g1)//3, (2*b0+b1)//3, 255), ((r0+2*r1)//3, (g0+2*g1)//3, (b0+2*b1)//3, 255)]
    else:
        pal = [(r0, g0, b0, 255), (r1, g1, b1, 255), ((r0+r1)//2, (g0+g1)//2, (b0+b1)//2, 255), (0, 0, 0, 0)]
    for i in range(16):
        x = bx*4 + (i & 3); y = by*4 + (i >> 2)
        if x >= w or y >= h: continue
        r, g, b, a = pal[(idx >> (2*i)) & 3]
        if alpha is not None: a = alpha[i]
        o = (y*w + x)*4; out[o] = r; out[o+1] = g; out[o+2] = b; out[o+3] = a

def dxt1(data, w, h):
    out = bytearray(w*h*4); bw = (w+3)//4; bh = (h+3)//4; p = 0
    for by in range(bh):
        for bx in range(bw): dxt1_block(data, p, out, w, h, bx, by); p += 8
    return out

def dxt5(data, w, h):
    out = bytearray(w*h*4); bw = (w+3)//4; bh = (h+3)//4; p = 0
    for by in range(bh):
        for bx in range(bw):
            a0 = data[p]; a1 = data[p+1]; bits = int.from_bytes(data[p+2:p+8], 'little')
            if a0 > a1: pal = [a0, a1] + [((7-i)*a0 + i*a1)//7 for i in range(1, 7)]
            else: pal = [a0, a1] + [((5-i)*a0 + i*a1)//5 for i in range(1, 5)] + [0, 255]
            alpha = [pal[(bits >> (3*i)) & 7] for i in range(16)]
            dxt1_block(data, p+8, out, w, h, bx, by, alpha=alpha, force4=True); p += 16
    return out

P2 = bytes([128,0,1,1,0,0,1,1,0,0,1,1,0,0,1,129,128,0,0,1,0,0,0,1,0,0,0,1,0,0,0,129,128,1,1,1,0,1,1,1,0,1,1,1,0,1,1,129,128,0,0,1,0,0,1,1,0,0,1,1,0,1,1,129,128,0,0,0,0,0,0,1,0,0,0,1,0,0,1,129,128,0,1,1,0,1,1,1,0,1,1,1,1,1,1,129,128,0,0,1,0,0,1,1,0,1,1,1,1,1,1,129,128,0,0,0,0,0,0,1,0,0,1,1,0,1,1,129,128,0,0,0,0,0,0,0,0,0,0,1,0,0,1,129,128,0,1,1,0,1,1,1,1,1,1,1,1,1,1,129,128,0,0,0,0,0,0,1,0,1,1,1,1,1,1,129,128,0,0,0,0,0,0,0,0,0,0,1,0,1,1,129,128,0,0,1,0,1,1,1,1,1,1,1,1,1,1,129,128,0,0,0,0,0,0,0,1,1,1,1,1,1,1,129,128,0,0,0,1,1,1,1,1,1,1,1,1,1,1,129,128,0,0,0,0,0,0,0,0,0,0,0,1,1,1,129,128,0,0,0,1,0,0,0,1,1,1,0,1,1,1,129,128,1,129,1,0,0,0,1,0,0,0,0,0,0,0,0,128,0,0,0,0,0,0,0,129,0,0,0,1,1,1,0,128,1,129,1,0,0,1,1,0,0,0,1,0,0,0,0,128,0,129,1,0,0,0,1,0,0,0,0,0,0,0,0,128,0,0,0,1,0,0,0,129,1,0,0,1,1,1,0,128,0,0,0,0,0,0,0,129,0,0,0,1,1,0,0,128,1,1,1,0,0,1,1,0,0,1,1,0,0,0,129,128,0,129,1,0,0,0,1,0,0,0,1,0,0,0,0,128,0,0,0,1,0,0,0,129,0,0,0,1,1,0,0,128,1,129,0,0,1,1,0,0,1,1,0,0,1,1,0,128,0,129,1,0,1,1,0,0,1,1,0,1,1,0,0,128,0,0,1,0,1,1,1,129,1,1,0,1,0,0,0,128,0,0,0,1,1,1,1,129,1,1,1,0,0,0,0,128,1,129,1,0,0,0,1,1,0,0,0,1,1,1,0,128,0,129,1,1,0,0,1,1,0,0,1,1,1,0,0,128,1,0,1,0,1,0,1,0,1,0,1,0,1,0,129,128,0,0,0,1,1,1,1,0,0,0,0,1,1,1,129,128,1,0,1,1,0,129,0,0,1,0,1,1,0,1,0,128,0,1,1,0,0,1,1,129,1,0,0,1,1,0,0,128,0,129,1,1,1,0,0,0,0,1,1,1,1,0,0,128,1,0,1,0,1,0,1,129,0,1,0,1,0,1,0,128,1,1,0,1,0,0,1,0,1,1,0,1,0,0,129,128,1,0,1,1,0,1,0,1,0,1,0,0,1,0,129,128,1,129,1,0,0,1,1,1,1,0,0,1,1,1,0,128,0,0,1,0,0,1,1,129,1,0,0,1,0,0,0,128,0,129,1,0,0,1,0,0,1,0,0,1,1,0,0,128,0,129,1,1,0,1,1,1,1,0,1,1,1,0,0,128,1,129,0,1,0,0,1,1,0,0,1,0,1,1,0,128,0,1,1,1,1,0,0,1,1,0,0,0,0,1,129,128,1,1,0,0,1,1,0,1,0,0,1,1,0,0,129,128,0,0,0,0,1,129,0,0,1,1,0,0,0,0,0,128,1,0,0,1,1,129,0,0,1,0,0,0,0,0,0,128,0,129,0,0,1,1,1,0,0,1,0,0,0,0,0,128,0,0,0,0,0,129,0,0,1,1,1,0,0,1,0,128,0,0,0,0,1,0,0,129,1,1,0,0,1,0,0,128,1,1,0,1,1,0,0,1,0,0,1,0,0,1,129,128,0,1,1,0,1,1,0,1,1,0,0,1,0,0,129,128,1,129,0,0,0,1,1,1,0,0,1,1,1,0,0,128,0,129,1,1,0,0,1,1,1,0,0,0,1,1,0,128,1,1,0,1,1,0,0,1,1,0,0,1,0,0,129,128,1,1,0,0,0,1,1,0,0,1,1,1,0,0,129,128,1,1,1,1,1,1,0,1,0,0,0,0,0,0,129,128,0,0,1,1,0,0,0,1,1,1,0,0,1,1,129,128,0,0,0,1,1,1,1,0,0,1,1,0,0,1,129,128,0,129,1,0,0,1,1,1,1,1,1,0,0,0,0,128,0,129,0,0,0,1,0,1,1,1,0,1,1,1,0,128,1,0,0,0,1,0,0,0,1,1,1,0,1,1,129])
P3 = bytes([128,0,1,129,0,0,1,1,0,2,2,1,2,2,2,130,128,0,0,129,0,0,1,1,130,2,1,1,2,2,2,1,128,0,0,0,2,0,0,1,130,2,1,1,2,2,1,129,128,2,2,130,0,0,2,2,0,0,1,1,0,1,1,129,128,0,0,0,0,0,0,0,129,1,2,2,1,1,2,130,128,0,1,129,0,0,1,1,0,0,2,2,0,0,2,130,128,0,2,130,0,0,2,2,1,1,1,1,1,1,1,129,128,0,1,1,0,0,1,1,130,2,1,1,2,2,1,129,128,0,0,0,0,0,0,0,129,1,1,1,2,2,2,130,128,0,0,0,1,1,1,1,129,1,1,1,2,2,2,130,128,0,0,0,1,1,129,1,2,2,2,2,2,2,2,130,128,0,1,2,0,0,129,2,0,0,1,2,0,0,1,130,128,1,1,2,0,1,129,2,0,1,1,2,0,1,1,130,128,1,2,2,0,129,2,2,0,1,2,2,0,1,2,130,128,0,1,129,0,1,1,2,1,1,2,2,1,2,2,130,128,0,1,129,2,0,0,1,130,2,0,0,2,2,2,0,128,0,0,129,0,0,1,1,0,1,1,2,1,1,2,130,128,1,1,129,0,0,1,1,130,0,0,1,2,2,0,0,128,0,0,0,1,1,2,2,129,1,2,2,1,1,2,130,128,0,2,130,0,0,2,2,0,0,2,2,1,1,1,129,128,1,1,129,0,1,1,1,0,2,2,2,0,2,2,130,128,0,0,129,0,0,0,1,130,2,2,1,2,2,2,1,128,0,0,0,0,0,129,1,0,1,2,2,0,1,2,130,128,0,0,0,1,1,0,0,130,2,129,0,2,2,1,0,128,1,2,130,0,129,2,2,0,0,1,1,0,0,0,0,128,0,1,2,0,0,1,2,129,1,2,2,2,2,2,130,128,1,1,0,1,2,130,1,129,2,2,1,0,1,1,0,128,0,0,0,0,1,129,0,1,2,130,1,1,2,2,1,128,0,2,2,1,1,0,2,129,1,0,2,0,0,2,130,128,1,1,0,0,129,1,0,2,0,0,2,2,2,2,130,128,0,1,1,0,1,2,2,0,1,130,2,0,0,1,129,128,0,0,0,2,0,0,0,130,2,1,1,2,2,2,129,128,0,0,0,0,0,0,2,129,1,2,2,1,2,2,130,128,2,2,130,0,0,2,2,0,0,1,2,0,0,1,129,128,0,1,129,0,0,1,2,0,0,2,2,0,2,2,130,128,1,2,0,0,129,2,0,0,1,130,0,0,1,2,0,128,0,0,0,1,1,129,1,2,2,130,2,0,0,0,0,128,1,2,0,1,2,0,1,130,0,129,2,0,1,2,0,128,1,2,0,2,0,1,2,129,130,0,1,0,1,2,0,128,0,1,1,2,2,0,0,1,1,130,2,0,0,1,129,128,0,1,1,1,1,130,2,2,2,0,0,0,0,1,129,128,1,0,129,0,1,0,1,2,2,2,2,2,2,2,130,128,0,0,0,0,0,0,0,130,1,2,1,2,1,2,129,128,0,2,2,1,129,2,2,0,0,2,2,1,1,2,130,128,0,2,130,0,0,1,1,0,0,2,2,0,0,1,129,128,2,2,0,1,2,130,1,0,2,2,0,1,2,2,129,128,1,0,1,2,2,130,2,2,2,2,2,0,1,0,129,128,0,0,0,2,1,2,1,130,1,2,1,2,1,2,129,128,1,0,129,0,1,0,1,0,1,0,1,2,2,2,130,128,2,2,130,0,1,1,1,0,2,2,2,0,1,1,129,128,0,0,2,1,129,1,2,0,0,0,2,1,1,1,130,128,0,0,0,2,129,1,2,2,1,1,2,2,1,1,130,128,2,2,2,0,129,1,1,0,1,1,1,0,2,2,130,128,0,0,2,1,1,1,2,129,1,1,2,0,0,0,130,128,1,1,0,0,129,1,0,0,1,1,0,2,2,2,130,128,0,0,0,0,0,0,0,2,1,129,2,2,1,1,130,128,1,1,0,0,129,1,0,2,2,2,2,2,2,2,130,128,0,2,2,0,0,1,1,0,0,129,1,0,0,2,130,128,0,2,2,1,1,2,2,129,1,2,2,0,0,2,130,128,0,0,0,0,0,0,0,0,0,0,0,2,129,1,130,128,0,0,130,0,0,0,1,0,0,0,2,0,0,0,129,128,2,2,2,1,2,2,2,0,2,2,2,129,2,2,130,128,1,0,129,2,2,2,2,2,2,2,2,2,2,2,130,128,1,1,129,2,0,1,1,130,2,0,1,2,2,2,0])
W2 = [0, 21, 43, 64]; W3 = [0, 9, 18, 27, 37, 46, 55, 64]; W4 = [0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64]
BITS_RGB = [4, 6, 5, 7, 5, 7, 7, 5]; BITS_A = [0, 0, 0, 0, 6, 8, 7, 5]; HAS_P = 0b11001011
def interp(a, b, wt, i): return (a*(64-wt[i]) + b*wt[i] + 32) >> 6

def bc7_block(data, p, out, w, h, bx, by):
    v = int.from_bytes(data[p:p+16], 'little'); pos = 0
    def rd(n):
        nonlocal pos
        r = (v >> pos) & ((1 << n) - 1); pos += n; return r
    mode = 0
    while mode < 8 and rd(1) == 0: mode += 1
    if mode >= 8:
        for i in range(16):
            x = bx*4 + (i & 3); y = by*4 + (i >> 2)
            if x < w and y < h: o = (y*w+x)*4; out[o:o+4] = b'\0\0\0\0'
        return
    partition = 0; nparts = 1; rotation = 0; isb = 0
    if mode in (0, 1, 2, 3, 7):
        nparts = 3 if mode in (0, 2) else 2
        partition = rd(4 if mode == 0 else 6)
    nend = nparts * 2
    if mode in (4, 5):
        rotation = rd(2)
        if mode == 4: isb = rd(1)
    ep = [[0, 0, 0, 0] for _ in range(6)]
    for c in range(3):
        for j in range(nend): ep[j][c] = rd(BITS_RGB[mode])
    if BITS_A[mode]:
        for j in range(nend): ep[j][3] = rd(BITS_A[mode])
    if mode in (0, 1, 3, 6, 7):
        for i in range(nend):
            for j in range(4): ep[i][j] <<= 1
        if mode == 1:
            i = rd(1); j = rd(1)
            for k in range(3): ep[0][k] |= i; ep[1][k] |= i; ep[2][k] |= j; ep[3][k] |= j
        elif HAS_P & (1 << mode):
            for i in range(nend):
                j = rd(1)
                for k in range(4): ep[i][k] |= j
    for i in range(nend):
        j = BITS_RGB[mode] + ((HAS_P >> mode) & 1)
        for k in range(3):
            ep[i][k] = (ep[i][k] << (8 - j)) & 0xff; ep[i][k] |= ep[i][k] >> j
        j = BITS_A[mode] + ((HAS_P >> mode) & 1)
        ep[i][3] = (ep[i][3] << (8 - j)) & 0xff if j else 0; ep[i][3] |= (ep[i][3] >> j) if j else 0
    if not BITS_A[mode]:
        for j in range(nend): ep[j][3] = 255
    ib = 3 if mode in (0, 1) else (4 if mode == 6 else 2)
    ib2 = 3 if mode == 4 else (2 if mode == 5 else 0)
    wt = W2 if ib == 2 else (W3 if ib == 3 else W4); wt2 = W2 if ib2 == 2 else W3
    table = None if nparts == 1 else (P2 if nparts == 2 else P3)
    idx = [0]*16
    for i in range(16):
        ps = (0 if i else 128) if nparts == 1 else table[partition*16 + i]
        n = ib - (1 if ps & 0x80 else 0)
        idx[i] = rd(n)
    for i in range(16):
        ps = (0 if i else 128) if nparts == 1 else table[partition*16 + i]
        ps &= 3; index = idx[i]; e0 = ep[ps*2]; e1 = ep[ps*2+1]
        if not ib2:
            r = interp(e0[0], e1[0], wt, index); g = interp(e0[1], e1[1], wt, index); b = interp(e0[2], e1[2], wt, index); a = interp(e0[3], e1[3], wt, index)
        else:
            index2 = rd(ib2 if i else ib2 - 1)
            if not isb:
                r = interp(e0[0], e1[0], wt, index); g = interp(e0[1], e1[1], wt, index); b = interp(e0[2], e1[2], wt, index); a = interp(e0[3], e1[3], wt2, index2)
            else:
                r = interp(e0[0], e1[0], wt2, index2); g = interp(e0[1], e1[1], wt2, index2); b = interp(e0[2], e1[2], wt2, index2); a = interp(e0[3], e1[3], wt, index)
        if rotation == 1: a, r = r, a
        elif rotation == 2: a, g = g, a
        elif rotation == 3: a, b = b, a
        x = bx*4 + (i & 3); y = by*4 + (i >> 2)
        if x < w and y < h:
            o = (y*w+x)*4; out[o] = r; out[o+1] = g; out[o+2] = b; out[o+3] = a

def bc7(data, w, h):
    out = bytearray(w*h*4); bw = (w+3)//4; bh = (h+3)//4; p = 0
    for by in range(bh):
        for bx in range(bw): bc7_block(data, p, out, w, h, bx, by); p += 16
    return out

def raw(data, w, h, fmt):
    out = bytearray(w*h*4)
    for i in range(w*h):
        if fmt == 4: out[i*4:i*4+4] = data[i*4:i*4+4]                       # RGBA32
        elif fmt == 5: out[i*4:i*4+3] = data[i*4+1:i*4+4]; out[i*4+3] = data[i*4]   # ARGB32
        elif fmt == 3: out[i*4:i*4+3] = data[i*3:i*3+3]; out[i*4+3] = 255   # RGB24
        elif fmt == 1: out[i*4:i*4+3] = b'\xff\xff\xff'; out[i*4+3] = data[i]  # Alpha8
    return out

def decode(data, w, h, fmt):
    if fmt == 10: return dxt1(data, w, h)
    if fmt == 12: return dxt5(data, w, h)
    if fmt == 25: return bc7(data, w, h)
    if fmt in (1, 3, 4, 5): return raw(data, w, h, fmt)
    return None

def flip(rgba, w, h):
    # Unity stores bottom row first
    out = bytearray(w*h*4)
    for y in range(h): out[y*w*4:(y+1)*w*4] = rgba[(h-1-y)*w*4:(h-y)*w*4]
    return out

def downscale(rgba, w, h, maxs):
    step = 1
    while w // step > maxs or h // step > maxs: step *= 2
    if step == 1: return rgba, w, h
    ow = w // step; oh = h // step; out = bytearray(ow*oh*4); n = step*step
    for y in range(oh):
        for x in range(ow):
            r = g = b = a = 0
            for yy in range(step):
                row = ((y*step+yy)*w + x*step)*4
                for xx in range(step):
                    o = row + xx*4; r += rgba[o]; g += rgba[o+1]; b += rgba[o+2]; a += rgba[o+3]
            o = (y*ow+x)*4; out[o] = r//n; out[o+1] = g//n; out[o+2] = b//n; out[o+3] = a//n
    return out, ow, oh

def png(rgba, w, h):
    stride = w*4; raw = bytearray()
    for y in range(h): raw += b'\0' + rgba[y*stride:(y+1)*stride]
    def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes(raw), 6)) + chunk(b'IEND', b'')


# ------------------------------------------------------------------ main
def safe_name(name): return "tex_" + re.sub(r"[^a-zA-Z0-9_-]", "_", name) + ".png"

def asset_files(data_dir):
    out = []
    for sub in (os.path.join(data_dir, "StreamingAssets", "SoftRef", "Bundles"), os.path.join(data_dir, "StreamingAssets", "aa")):
        if os.path.isdir(sub):
            for root, _, files in os.walk(sub): out += [os.path.join(root, f) for f in files]
    out.sort(key=lambda p: -os.path.getsize(p))
    out += [os.path.join(data_dir, f) for f in sorted(os.listdir(data_dir)) if f.endswith(".assets") or f == "globalgamemanagers"]
    return out

def is_bundle(path):
    with open(path, 'rb') as f: return f.read(7) == b'UnityFS'

def extract_from(path, wanted, outdir, size):
    found = 0
    if is_bundle(path):
        b = Bundle(path)
        try:
            for name, (off, sz) in b.nodes.items():
                if not wanted: break
                if name.endswith(('.resS', '.resource')) or sz < 48: continue
                data = b.node(name)
                if not looks_serialized(data): continue
                found += extract_serialized(data, lambda p, o, s: b.read(b.nodes[p.split('/')[-1]][0] + o, s), wanted, outdir, size)
        finally: b.close()
    else:
        data = open(path, 'rb').read()
        if not looks_serialized(data): return 0
        def ext(p, o, s):
            with open(os.path.join(os.path.dirname(path), p.split('/')[-1]), 'rb') as f: f.seek(o); return f.read(s)
        found += extract_serialized(data, ext, wanted, outdir, size)
    return found

def extract_serialized(data, stream_read, wanted, outdir, size):
    types, objs = parse(data); found = 0
    for o in objs:
        cid, nodes = types[o[3]]
        if cid != 28 or nodes is None: continue
        v, _ = read_value(LE(data, o[1]), nodes, 0)
        name = v.get('m_Name')
        if name not in wanted: continue
        w, h, fmt = v['m_Width'], v['m_Height'], v['m_TextureFormat']
        img = v.get('image data') or b''
        if not img:
            sd = v['m_StreamData']
            try: img = stream_read(sd['path'], sd['offset'], sd['size'])
            except Exception as e: print(f"  {name}: stream read failed ({e})"); continue
        rgba = decode(img, w, h, fmt)
        if rgba is None: print(f"  {name}: format {fmt} not supported"); wanted.discard(name); continue
        rgba = flip(rgba, w, h); rgba, ow, oh = downscale(rgba, w, h, size)
        with open(os.path.join(outdir, wanted[name] if isinstance(wanted, dict) else safe_name(name)), 'wb') as f: f.write(png(rgba, ow, oh))
        print(f"  {name} {w}x{h} fmt {fmt} -> {ow}x{oh}")
        if isinstance(wanted, dict): del wanted[name]
        else: wanted.discard(name)
        found += 1
    return found

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_dir"); ap.add_argument("models_dir")
    ap.add_argument("--size", type=int, default=512); ap.add_argument("--all", action="store_true"); ap.add_argument("--names")
    a = ap.parse_args()
    if not os.path.isdir(a.data_dir): sys.exit(f"not a directory: {a.data_dir}")
    os.makedirs(a.models_dir, exist_ok=True)
    if a.names: wanted = {n.strip(): safe_name(n.strip()) for n in a.names.split(",") if n.strip()}
    else:
        tj = os.path.join(a.models_dir, "textures.json")
        if not os.path.isfile(tj): sys.exit(f"{tj} not found: start the server once so the mod lists what it needs")
        doc = json.load(open(tj, encoding="utf-8"))
        if doc.get("enabled") is False and not a.all: print("use_textures is off in the mod config; nothing to do (--all to extract anyway)"); return
        wanted = {t["name"]: t["file"] for t in doc.get("textures", []) if a.all or not t.get("present")}
    if not wanted: print("nothing to do: every referenced texture is already present"); return
    print(f"{len(wanted)} texture(s) wanted"); t0 = time.time(); total = 0
    for path in asset_files(a.data_dir):
        if not wanted: break
        try: total += extract_from(path, wanted, a.models_dir, a.size)
        except Exception as e: print(f"  skip {os.path.basename(path)}: {e}")
    print(f"wrote {total} texture(s) in {time.time() - t0:.0f}s" + (f"; not found: {', '.join(sorted(wanted))}" if wanted else ""))

if __name__ == "__main__":
    main()
