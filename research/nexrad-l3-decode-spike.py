#!/usr/bin/env python3
"""Feasibility spike: parse a NEXRAD Level III (NIDS) digital radial product
(p94 base reflectivity / p99 velocity / 165 hydro class) with stdlib only.
Refs: NWS/ROC ICD for RPG to Class 1 User (2620001), packet code 16."""
import struct, sys, zlib, bz2

def parse(path):
    raw = open(path, "rb").read()
    # Strip WMO header: two \r\r\n-terminated text lines.
    i = raw.find(b"\r\r\n"); j = raw.find(b"\r\r\n", i + 3)
    awips = raw[i+3:j].decode()
    body = raw[j+3:]
    # Some distributions zlib-compress the remainder.
    if body[:1] == b"\x78":
        out = b""
        d = zlib.decompressobj()
        out += d.decompress(body)
        while d.unused_data[:1] == b"\x78":
            nd = zlib.decompressobj(); out += nd.decompress(d.unused_data); d = nd
        body = out
        # after decompress there may be an inner WMO header again
        k = body.find(b"\r\r\n"); k2 = body.find(b"\r\r\n", k + 3)
        if 0 <= k < 40: body = body[k2+3:]
    # Message Header Block (18B): code, date(mod Julian), time(s), len, src, dst, nblocks
    code, date, time_s, mlen, src, dst, nblk = struct.unpack(">hHIIhhh", body[:18])
    # Product Description Block (102B) starts with divider -1
    pdb = body[18:120]
    div, lat, lon, height, pcode, opmode = struct.unpack(">hiih hh", pdb[:16])
    vcp, = struct.unpack(">h", pdb[16:18])
    # halfwords 31-46 of message: data level thresholds (digital: scale/offset)
    thr = struct.unpack(">16h", pdb[42:74])
    off_sym, = struct.unpack(">I", pdb[90:94])  # halfword offset from msg start
    sym = body[off_sym*2:]
    if sym[:2] != b"\xff\xff":  # divider -1
        # symbology block may be bzip2/zlib compressed (product-dependent)
        if sym[:2] == b"BZ": sym = bz2.decompress(sym)
    div2, blkid, blklen, nlayers = struct.unpack(">hhIh", sym[:10])
    lay_div, lay_len = struct.unpack(">hI", sym[10:16])
    pkt = sym[16:16+lay_len]
    pcode16, = struct.unpack(">H", pkt[:2])
    assert pcode16 == 16, f"packet {pcode16}, expected 16 (digital radial data array)"
    first_bin, nbins, icent, jcent, scale, nrad = struct.unpack(">6h", pkt[2:14])
    radials = []
    p = 14
    for _ in range(nrad):
        nb, az10, daz10 = struct.unpack(">3h", pkt[p:p+6]); p += 6
        data = pkt[p:p+nb]; p += nb
        if nb % 2: p += 1  # halfword padding
        radials.append((az10 / 10.0, daz10 / 10.0, data))
    return awips, code, lat/1000, lon/1000, vcp, nbins, nrad, thr, radials

for path in sys.argv[1:]:
    awips, code, lat, lon, vcp, nbins, nrad, thr, radials = parse(path)
    # digital reflectivity: thr[0]=min*10? For p94: scale = thr halfwords 31/32.
    az, daz, data = radials[0]
    mx = max(max(r[2]) for r in radials)
    print(f"{path}: {awips} prod={code} site=({lat:.3f},{lon:.3f}) VCP={vcp} "
          f"radials={nrad} bins={nbins} thr[:4]={thr[:4]} maxlevel={mx}")
    if code == 94:
        # p94 level->dBZ: dBZ = (level - 2)*0.5 - 32  (levels 0=below thr, 1=RF)
        print(f"  max dBZ on scope: {(mx-2)*0.5-32:.1f} (radial0 az={az})")
