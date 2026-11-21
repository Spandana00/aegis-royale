"""Map geometry, sight/shot tests and path planning. OWNER: nav.

Design (details and timings in docs/nav.md):

* Solids come straight from world.json: every prism ring/hole edge goes into a 16 m uniform grid. A segment
  test gathers the edges of the cells the segment crosses (DDA), then runs one vectorised 2D segment/edge
  intersection; a crossing at a height inside [base, top] is a wall hit. Two rare cases are handled exactly
  in Python: a segment that passes through a thin slab (bridge deck) without touching a side face inside its
  height range, and an endpoint inside a solid. Terrain is sampled every 1 m (bilinear) only where the
  segment dips below the per-cell terrain maximum.
* Trees affect vision only (`los`, `can_see`): crowns are ellipsoids with optical density
  `rules.canopyDensity` per metre; sight is blocked when exp(-density * chord) < `rules.canopyBlockT`.
  Trunks (cylinders up to the crown base) block sight. Shots ignore trees.
* Navigation uses bot/navbake.npz (tools/nav/bake.py): a 1 m surface/clearance/walkable grid and a 4 m
  lattice graph per mech size class. `plan` is a budgeted, resumable reverse weighted A* (searches are kept per
  goal, so repeated calls with a moving start finish the search across ticks), then string-pulled with
  vectorised walk-line checks. Without the bake every nav query degrades to straight lines.

Every public method is exception-safe from the caller's point of view only by convention: callers wrap
calls (main.py does); methods here avoid raising on bad input where cheap.
"""
from __future__ import annotations

import array
import hashlib
import heapq
import json
import math
import os
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

Vec3 = Sequence[float]

HERE = os.path.dirname(os.path.abspath(__file__))
CELL = 16.0                      # solid/tree grid cell (m)
STEP_UP = 1.2
SQ2 = math.sqrt(2.0)
DIRS = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
REV = (4, 5, 6, 7, 0, 1, 2, 3)   # index of the opposite direction


def _log(*a):
    try:
        print("[arena]", *a, file=sys.stderr, flush=True)
    except Exception:
        pass


def size_scale(cubes: float) -> float:
    return 1.0 + 0.05 * max(0.0, float(cubes or 0))


class _Search:
    """Resumable reverse weighted A* from a goal node toward a (moving) start node on one size class."""
    __slots__ = ("goal", "k", "target", "open", "g", "parent", "closed", "done_fail", "expanded", "t_last", "cap",
                 "avoid", "expo")

    def __init__(self, goal: int, k: int, target: int):
        self.goal, self.k, self.target = goal, k, target
        self.open: list = []
        self.g: Dict[int, float] = {goal: 0.0}
        self.parent: Dict[int, int] = {goal: -1}
        self.closed: set = set()
        self.done_fail = False
        self.cap = 40.0
        self.avoid = ()        # threat feet positions: nodes they can see cost extra
        self.expo: Dict[int, float] = {}
        self.expanded = 0
        self.t_last = 0.0


class _Flood:
    """Time-sliced multi-source reverse Dijkstra toward a circle (Arena.zone_field)."""
    __slots__ = ("k", "cx", "cy", "r", "heap", "dist", "closed", "done", "init_done", "scan", "t_used", "max_cost")

    def __init__(self, k, cx, cy, r):
        self.k, self.cx, self.cy, self.r = k, cx, cy, r
        self.heap: list = []
        self.dist: Dict[int, float] = {}
        self.closed: set = set()
        self.done = False
        self.init_done = False
        self.scan = None
        self.t_used = 0.0
        self.max_cost = 450.0       # metres (~38 s walking): beyond this nobody makes it anyway


class Arena:
    W_ASTAR = 1.4                 # heuristic weight (bounded-suboptimal, much faster)
    JET_FIXED = 25.0              # extra cost (m-equivalent) of any jump+jet hop: noise, energy, risk
    JET_PER_M = 1.5               # per metre climbed
    MAX_SEARCHES = 10

    # ------------------------------------------------------------------ loading
    def __init__(self):
        self.ok_nav = False
        self.last_raw_path: List[Tuple[float, float]] = []
        self.last_goal_snapped = True
        self.stats = {"plan_calls": 0, "plan_ms_max": 0.0, "seg_calls": 0}
        self._searches: Dict[Tuple[int, int], _Search] = {}
        self._floods: Dict[tuple, _Flood] = {}
        self._los_cache: Dict[tuple, bool] = {}
        self._cache_tick = None

    @classmethod
    def load(cls, map_dir: str, bake_path: Optional[str] = None) -> "Arena":
        t0 = time.perf_counter()
        a = cls()
        wpath = None
        for cand in (os.path.join(map_dir, "v2", "world.json"), os.path.join(map_dir, "world.json")):
            if os.path.exists(cand):
                wpath = cand
                break
        if wpath is None:
            raise FileNotFoundError(f"world.json not under {map_dir}")
        with open(wpath, "rb") as f:
            raw = f.read()
        a.world_sha1 = hashlib.sha1(raw).hexdigest()
        w = json.loads(raw)
        a._load_terrain(w, os.path.join(os.path.dirname(wpath), w["terrain"].get("file", "terrain.i16")))
        a._load_solids(w)
        a._load_trees(w)
        t1 = time.perf_counter()
        try:
            cands = [bake_path] if bake_path else [os.path.join(HERE, "navbake.npz"), "/app/cache/navbake.npz"]
            for c in cands:
                if c and os.path.exists(c):
                    a._load_bake(c)
                    break
        except Exception as e:  # pragma: no cover - degraded mode
            _log("nav bake failed, straight-line nav only:", repr(e))
            a.ok_nav = False
        a.load_s = time.perf_counter() - t0
        _log(f"loaded in {a.load_s * 1000:.0f} ms (geometry {1000 * (t1 - t0):.0f} ms, nav={'yes' if a.ok_nav else 'NO'})")
        return a

    def _load_terrain(self, w, path):
        t = w["terrain"]
        self.nx, self.ny = int(t["nx"]), int(t["ny"])
        self.x0, self.y0 = float(t["minX"]), float(t["minY"])
        self.step = float(t.get("step", 1.0))
        sc = float(t.get("scale", 0.01))
        self.H = (np.fromfile(path, "<i2").reshape(self.ny, self.nx).astype(np.float32) * sc)
        # array.array, not list: fast scalar access and invisible to the cyclic GC (no full-collection pauses)
        self._Hl = array.array("f", self.H.ravel().tobytes())
        b = w["bounds"]
        self.bounds = (float(b["minX"]), float(b["maxX"]), float(b["minY"]), float(b["maxY"]))
        rules = w.get("rules") or {}
        self.canopy_density = float(rules.get("canopyDensity", 0.35))
        self.canopy_block_t = float(rules.get("canopyBlockT", 0.25))
        # grid for solids/trees/terrain maxima
        self.gx0, self.gy0 = self.x0, self.y0
        self.GX = int(math.ceil(self.nx * self.step / CELL)) + 1
        self.GY = int(math.ceil(self.ny * self.step / CELL)) + 1
        tmax = np.full((self.GY, self.GX), -1e9, np.float32)
        c = int(CELL / self.step)
        for gj in range(self.GY):
            j0, j1 = gj * c, min(self.ny, gj * c + c + 1)
            if j0 >= self.ny:
                continue
            row = self.H[j0:j1]
            for gi in range(self.GX):
                i0, i1 = gi * c, min(self.nx, gi * c + c + 1)
                if i0 < self.nx:
                    tmax[gj, gi] = row[:, i0:i1].max()
        self.cell_tmax = array.array("f", tmax.ravel().tobytes())

    def _load_solids(self, w):
        prisms = w.get("prisms") or []
        self.prisms = prisms
        self.p_base = [float(p["base"]) for p in prisms]
        self.p_top = [float(p["top"]) for p in prisms]
        self.p_kind = [p.get("kind", "building") for p in prisms]
        self.p_rings = []      # list of lists of (xs, ys) python lists (ring first, then holes)
        self.p_bbox = []
        ax, ay, bx, by, pid = [], [], [], [], []
        for k, p in enumerate(prisms):
            rings = [p["ring"]] + list(p.get("holes") or [])
            rl = []
            for r in rings:
                xs, ys = [float(v) for v in r[0::2]], [float(v) for v in r[1::2]]
                rl.append((xs, ys))
                n = len(xs)
                for i in range(n):
                    j = (i + 1) % n
                    ax.append(xs[i]); ay.append(ys[i]); bx.append(xs[j]); by.append(ys[j]); pid.append(k)
            self.p_rings.append(rl)
            xs0, ys0 = rl[0]
            self.p_bbox.append((min(xs0), min(ys0), max(xs0), max(ys0)))
        self.EAX, self.EAY = np.array(ax), np.array(ay)
        self.EBX, self.EBY = np.array(bx), np.array(by)
        self.EP = np.array(pid, np.int32)
        self.EBASE = np.array(self.p_base)[self.EP] if len(pid) else np.zeros(0)
        self.ETOP = np.array(self.p_top)[self.EP] if len(pid) else np.zeros(0)
        # edge -> cells (supercover by dense sampling)
        cell_edges: Dict[int, list] = {}
        cell_prisms: Dict[int, set] = {}
        for e in range(len(ax)):
            L = math.hypot(bx[e] - ax[e], by[e] - ay[e])
            n = int(L / (CELL * 0.25)) + 2
            seen = set()
            for s in range(n):
                f = s / (n - 1)
                c = self._cell_of(ax[e] + (bx[e] - ax[e]) * f, ay[e] + (by[e] - ay[e]) * f)
                if c >= 0 and c not in seen:
                    seen.add(c)
                    cell_edges.setdefault(c, []).append(e)
        # prisms whose footprint bbox overlaps a cell (for endpoint-inside tests)
        for k, (x0, y0, x1, y1) in enumerate(self.p_bbox):
            i0, j0 = self._cell_ij(x0, y0)
            i1, j1 = self._cell_ij(x1, y1)
            for gj in range(max(0, j0), min(self.GY, j1 + 1)):
                for gi in range(max(0, i0), min(self.GX, i1 + 1)):
                    cell_prisms.setdefault(gj * self.GX + gi, set()).add(k)
        self.cell_edges = [None] * (self.GX * self.GY)
        self.cell_maxtop = [-1e9] * (self.GX * self.GY)
        self.cell_minbase = [1e9] * (self.GX * self.GY)
        for c, es in cell_edges.items():
            arr = np.array(sorted(es), np.int32)
            self.cell_edges[c] = arr
            self.cell_maxtop[c] = float(self.ETOP[arr].max())
            self.cell_minbase[c] = float(self.EBASE[arr].min())
        self.cell_prisms = [tuple(sorted(cell_prisms.get(c, ()))) for c in range(self.GX * self.GY)]

    def _load_trees(self, w):
        tr = w.get("trees") or {}
        fields = tr.get("fields") or []
        data = tr.get("data") or []
        nf = len(fields)
        self.n_trees = 0
        self.cell_trees = [None] * (self.GX * self.GY)
        if not nf or not data:
            return
        T = np.asarray(data, float).reshape(-1, nf)
        col = {f: i for i, f in enumerate(fields)}
        g = lambda name, d=0.0: T[:, col[name]] if name in col else np.full(len(T), d)  # noqa: E731
        self.TX, self.TY, self.TZ = g("x"), g("y"), g("z")
        self.TH, self.CR, self.CB, self.TR = g("height"), g("crownR"), g("crownBase"), g("trunkR", 0.3)
        self.CX = g("crownX") if "crownX" in col else self.TX
        self.CY = g("crownY") if "crownY" in col else self.TY
        self.CZ = self.TZ + 0.5 * (self.CB + self.TH)
        self.CHZ = np.maximum(0.5, 0.5 * (self.TH - self.CB))
        self.n_trees = len(T)
        # one gather per query: columns TX TY TZ CB TR CX CY CZ CR CHZ
        self.TREES = np.ascontiguousarray(np.stack([self.TX, self.TY, self.TZ, self.CB, self.TR, self.CX, self.CY,
                                                    self.CZ, np.maximum(self.CR, 0.3), self.CHZ], axis=1))
        cells: Dict[int, list] = {}
        for t in range(self.n_trees):
            r = max(self.CR[t], 0.5) + 0.5
            for x, y in ((self.CX[t], self.CY[t]), (self.TX[t], self.TY[t])):
                for dx in (-r, r):
                    for dy in (-r, r):
                        c = self._cell_of(x + dx, y + dy)
                        if c >= 0:
                            cells.setdefault(c, set()).add(t)
        for c, s in cells.items():
            self.cell_trees[c] = np.array(sorted(s), np.int32)

    def _load_bake(self, path):
        z = np.load(path)
        meta = json.loads(bytes(z["meta"]).decode())
        if meta.get("world_sha1") != self.world_sha1:
            _log("WARNING: nav bake was built for a different world.json; using it anyway")
        if (meta["nx"], meta["ny"]) != (self.nx, self.ny):
            raise ValueError("bake grid mismatch")
        self.meta = meta
        self.G = z["g"].astype(np.float32) / 100.0
        self._Gl = array.array("f", self.G.ravel().tobytes())
        self.KIND = z["kind"]
        self._Kb = self.KIND.tobytes()
        self.CEIL = z["ceil"]
        self.DW = z["dwall"]
        self._DWb = self.DW.tobytes()
        self.WALK = z["walk"]
        self._Wb = self.WALK.tobytes()
        self.COMP = z["comp"]
        self.block = int(meta["block"])
        self.scales = list(meta["scales"])
        self.r_plan = list(meta["r_plan"])
        node, em = z["node"], z["emask"]
        self.K = node.shape[0]
        self.BY, self.BX = node.shape[1], node.shape[2]
        self.node_off = [node[k].tobytes() for k in range(self.K)]
        self.emask = [em[k].tobytes() for k in range(self.K)]
        # node world positions + clearance penalty, per class
        B = self.block
        self.NXY = []
        self.NPEN = []
        self.NZ = []
        dwl = self.DW
        for k in range(self.K):
            off = node[k].astype(np.int32)
            has = off != 255
            bj, bi = np.nonzero(has)
            ox, oy = off[has] & 15, off[has] >> 4
            fi, fj = bi * B + ox, bj * B + oy
            xs = np.full(self.BX * self.BY, np.nan)
            ys = np.full(self.BX * self.BY, np.nan)
            ids = bj * self.BX + bi
            xs[ids] = self.x0 + fi * self.step
            ys[ids] = self.y0 + fj * self.step
            pen = np.zeros(self.BX * self.BY)
            d = dwl[np.minimum(fj, self.ny - 1), np.minimum(fi, self.nx - 1)] / 10.0
            # prefer open ground: up to +3 m per edge near walls
            pen[ids] = np.clip((self.r_plan[k] + 2.5 - d) * 1.2, 0, 3.0)
            self.NXY.append((array.array("d", xs.tobytes()), array.array("d", ys.tobytes())))
            self.NPEN.append(array.array("d", pen.tobytes()))
            nzv = np.full(self.BX * self.BY, np.nan)
            nzv[ids] = self.G[np.minimum(fj, self.ny - 1), np.minimum(fi, self.nx - 1)]
            self.NZ.append(array.array("d", nzv.tobytes()))
        self.DOFF = [di + dj * self.BX for di, dj in DIRS]
        self.DLEN = [B * (SQ2 if di and dj else 1.0) for di, dj in DIRS]
        self._DOFFSET = set(self.DOFF)
        self._dmap = {o: d for d, o in enumerate(self.DOFF)}
        jd = [tuple(v) for v in meta.get("jdirs", [])]
        self.JOFF = [di + dj * self.BX for di, dj in jd]
        self.JLEN = [B * math.hypot(di, dj) for di, dj in jd]
        self._jmap = {o: d for d, o in enumerate(self.JOFF)}
        if "jmask" in z.files and jd:
            self.jmask = [array.array("H", z["jmask"][k].astype("<u2").tobytes()) for k in range(self.K)]
            self.jclimb = [z["jclimb"][k].tobytes() for k in range(self.K)]
        else:
            self.jmask = [array.array("H", bytes(2 * self.BX * self.BY)) for _ in range(self.K)]
            self.jclimb = [bytes(self.BX * self.BY * max(1, len(jd))) for _ in range(self.K)]
        self.ok_nav = True

    # ------------------------------------------------------------------ small helpers
    def _cell_ij(self, x, y):
        return int((x - self.gx0) // CELL), int((y - self.gy0) // CELL)

    def _cell_of(self, x, y) -> int:
        gi, gj = int((x - self.gx0) // CELL), int((y - self.gy0) // CELL)
        if 0 <= gi < self.GX and 0 <= gj < self.GY:
            return gj * self.GX + gi
        return -1

    def _vidx(self, x, y) -> int:
        """Index of the nearest terrain vertex (clamped)."""
        i = int(round((x - self.x0) / self.step))
        j = int(round((y - self.y0) / self.step))
        i = 0 if i < 0 else (self.nx - 1 if i >= self.nx else i)
        j = 0 if j < 0 else (self.ny - 1 if j >= self.ny else j)
        return j * self.nx + i

    def in_bounds(self, x, y, margin=0.0) -> bool:
        b = self.bounds
        return b[0] + margin <= x <= b[1] - margin and b[2] + margin <= y <= b[3] - margin

    def new_tick(self, tick=None):
        """Optional: clear per-tick caches (called by navigate.step)."""
        if tick != self._cache_tick:
            self._cache_tick = tick
            if len(self._los_cache) > 4000 or tick is None:
                self._los_cache.clear()

    # ------------------------------------------------------------------ heights
    def height(self, x: float, y: float) -> float:
        """Terrain height (bilinear), ignoring prisms."""
        fx = (x - self.x0) / self.step
        fy = (y - self.y0) / self.step
        if fx < 0:
            fx = 0.0
        elif fx > self.nx - 1.001:
            fx = self.nx - 1.001
        if fy < 0:
            fy = 0.0
        elif fy > self.ny - 1.001:
            fy = self.ny - 1.001
        i, j = int(fx), int(fy)
        u, v = fx - i, fy - j
        H = self._Hl
        k = j * self.nx + i
        h00, h10 = H[k], H[k + 1]
        h01, h11 = H[k + self.nx], H[k + self.nx + 1]
        return (h00 * (1 - u) + h10 * u) * (1 - v) + (h01 * (1 - u) + h11 * u) * v

    def ground_z(self, x: float, y: float, z_hint: Optional[float] = None) -> float:
        """Top walkable surface at (x, y) at or below z_hint (+ step tolerance): roof, deck or terrain."""
        h = self.height(x, y)
        best = h
        for k in self._prisms_at(x, y):
            top = self.p_top[k]
            if top > best and (z_hint is None or top <= z_hint + 1.5) and self._inside_prism(k, x, y):
                if z_hint is None and self.p_base[k] > h + 9.0:
                    continue   # elevated deck: without a hint assume we are under it
                best = top
        return best

    def _prisms_at(self, x, y):
        c = self._cell_of(x, y)
        if c < 0:
            return ()
        out = []
        for k in self.cell_prisms[c]:
            b = self.p_bbox[k]
            if b[0] <= x <= b[2] and b[1] <= y <= b[3]:
                out.append(k)
        return out

    def _inside_prism(self, k, x, y) -> bool:
        inside = False
        for xs, ys in self.p_rings[k]:
            n = len(xs)
            j = n - 1
            for i in range(n):
                yi, yj = ys[i], ys[j]
                if (yi > y) != (yj > y):
                    xc = xs[i] + (y - yi) * (xs[j] - xs[i]) / (yj - yi)
                    if x < xc:
                        inside = not inside
                j = i
        return inside

    def inside_solid(self, p: Vec3) -> bool:
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        if z < self.height(x, y) - 0.05:
            return True
        for k in self._prisms_at(x, y):
            if self.p_base[k] < z < self.p_top[k] and self._inside_prism(k, x, y):
                return True
        return False

    # ------------------------------------------------------------------ segment tests
    def _cells_on_seg(self, ax, ay, bx, by) -> List[int]:
        """Grid cells touched by the 2D segment (Amanatides-Woo DDA)."""
        gx0, gy0 = self.gx0, self.gy0
        fx, fy = (ax - gx0) / CELL, (ay - gy0) / CELL
        tx, ty = (bx - gx0) / CELL, (by - gy0) / CELL
        i, j = int(math.floor(fx)), int(math.floor(fy))
        ie, je = int(math.floor(tx)), int(math.floor(ty))
        dx, dy = tx - fx, ty - fy
        si = 1 if dx > 0 else -1
        sj = 1 if dy > 0 else -1
        tdx = abs(1.0 / dx) if dx != 0 else 1e30
        tdy = abs(1.0 / dy) if dy != 0 else 1e30
        tmx = ((i + 1 - fx) if dx > 0 else (fx - i)) * tdx if dx != 0 else 1e30
        tmy = ((j + 1 - fy) if dy > 0 else (fy - j)) * tdy if dy != 0 else 1e30
        GX, GY = self.GX, self.GY
        out = []
        n = abs(ie - i) + abs(je - j) + 1
        for _ in range(n):
            if 0 <= i < GX and 0 <= j < GY:
                out.append(j * GX + i)
            if tmx < tmy:
                tmx += tdx
                i += si
            else:
                tmy += tdy
                j += sj
        return out

    def _seg_blocked(self, a: Vec3, b: Vec3, trees: bool = False, cells=None) -> bool:
        ax, ay, az = float(a[0]), float(a[1]), float(a[2])
        bx, by, bz = float(b[0]), float(b[1]), float(b[2])
        self.stats["seg_calls"] += 1
        if cells is None:
            cells = self._cells_on_seg(ax, ay, bx, by)
        zlo, zhi = (az, bz) if az < bz else (bz, az)
        # ---- prisms
        ce, mt, mb = self.cell_edges, self.cell_maxtop, self.cell_minbase
        parts = [ce[c] for c in cells if ce[c] is not None and mt[c] >= zlo and mb[c] <= zhi]
        if parts:
            ids = parts[0] if len(parts) == 1 else np.concatenate(parts)
            if self._edges_hit(ax, ay, az, bx, by, bz, ids):
                return True
        # endpoint inside a solid (rare: only near/over roofs)
        for (px, py, pz) in ((ax, ay, az), (bx, by, bz)):
            for k in self._prisms_at(px, py):
                if self.p_base[k] + 0.05 < pz < self.p_top[k] - 0.05 and self._inside_prism(k, px, py):
                    return True
        # ---- terrain
        tm = self.cell_tmax
        if any(tm[c] > zlo - 0.5 for c in cells):
            if self._terrain_hit(ax, ay, az, bx, by, bz):
                return True
        # ---- trees (vision only)
        if trees and self.n_trees:
            if self._trees_block(ax, ay, az, bx, by, bz, cells):
                return True
        return False

    def _edges_hit(self, ax, ay, az, bx, by, bz, ids) -> bool:
        dx, dy = bx - ax, by - ay
        eax, eay = self.EAX[ids], self.EAY[ids]
        ex, ey = self.EBX[ids] - eax, self.EBY[ids] - eay
        den = dx * ey - dy * ex
        wx, wy = eax - ax, eay - ay
        den = np.where(den == 0.0, 1e-300, den)
        t = (wx * ey - wy * ex) / den
        u = (wx * dy - wy * dx) / den
        hit = (t >= 0.0) & (t <= 1.0) & (u >= 0.0) & (u <= 1.0)
        if not hit.any():
            return False
        t = t[hit]
        idh = ids[hit]
        z = az + (bz - az) * t
        if ((z >= self.EBASE[idh]) & (z <= self.ETOP[idh])).any():
            return True
        # pass-through of a slab between two side crossings (enter above top, leave below base or reverse)
        if az == bz:
            return False
        pids = self.EP[idh]
        for k in set(pids.tolist()):
            m = pids == k
            zk = z[m]
            base, top = self.p_base[k], self.p_top[k]
            if zk.min() < base and zk.max() > top:
                tk = np.sort(t[m])
                inside0 = self._inside_prism(k, ax, ay)
                bounds = [0.0] + tk.tolist() + [1.0]
                ins = inside0
                for q in range(len(bounds) - 1):
                    if ins:
                        z0 = az + (bz - az) * bounds[q]
                        z1 = az + (bz - az) * bounds[q + 1]
                        if min(z0, z1) <= top and max(z0, z1) >= base:
                            return True
                    ins = not ins
        return False

    def _terrain_hit(self, ax, ay, az, bx, by, bz) -> bool:
        L = math.hypot(bx - ax, by - ay)
        n = int(L / self.step) + 2
        if n <= 2:
            return False
        t = np.linspace(0.0, 1.0, n)[1:-1]
        # ignore the first/last 0.6 m (feet-level endpoints sit on the bilinear surface)
        if L > 1.5:
            m = (t * L > 0.6) & ((1 - t) * L > 0.6)
            t = t[m]
        if t.size == 0:
            return False
        xs = ax + (bx - ax) * t
        ys = ay + (by - ay) * t
        zs = az + (bz - az) * t
        fx = np.clip((xs - self.x0) / self.step, 0, self.nx - 1.001)
        fy = np.clip((ys - self.y0) / self.step, 0, self.ny - 1.001)
        i = fx.astype(np.int32)
        j = fy.astype(np.int32)
        u, v = fx - i, fy - j
        H = self.H
        h = (H[j, i] * (1 - u) + H[j, i + 1] * u) * (1 - v) + (H[j + 1, i] * (1 - u) + H[j + 1, i + 1] * u) * v
        return bool((zs < h - 0.05).any())

    def _trees_block(self, ax, ay, az, bx, by, bz, cells) -> bool:
        ct = self.cell_trees
        parts = [ct[c] for c in cells if ct[c] is not None]
        if not parts:
            return False
        ids = np.unique(np.concatenate(parts)) if len(parts) > 1 else parts[0]
        dx, dy, dz = bx - ax, by - ay, bz - az
        P = self.TREES[ids]
        tx, ty, tz, cb, tr, ccx, ccy, ccz, cr, hz = P.T
        # trunks: vertical cylinders from z to z + crownBase
        L2 = dx * dx + dy * dy
        if L2 > 1e-9:
            s = np.clip(((tx - ax) * dx + (ty - ay) * dy) / L2, 0.0, 1.0)
            d = np.hypot(ax + dx * s - tx, ay + dy * s - ty)
            zs = az + dz * s
            if ((d <= tr) & (zs >= tz) & (zs <= tz + cb)).any():
                return True
        # crowns: ellipsoid chords
        px, py, pz = (ax - ccx) / cr, (ay - ccy) / cr, (az - ccz) / hz
        qx, qy, qz = dx / cr, dy / cr, dz / hz
        A = qx * qx + qy * qy + qz * qz
        Bq = 2 * (px * qx + py * qy + pz * qz)
        C = px * px + py * py + pz * pz - 1.0
        disc = Bq * Bq - 4 * A * C
        m = disc > 0
        if not m.any():
            return False
        sq = np.sqrt(disc[m])
        A2 = 2 * A[m]
        t1 = np.clip((-Bq[m] - sq) / A2, 0.0, 1.0)
        t2 = np.clip((-Bq[m] + sq) / A2, 0.0, 1.0)
        chord = float(((t2 - t1).clip(min=0)).sum()) * math.sqrt(dx * dx + dy * dy + dz * dz)
        return math.exp(-self.canopy_density * chord) < self.canopy_block_t

    def shot_clear(self, a: Vec3, b: Vec3) -> bool:
        """Projectile/beam path a->b clear of prisms and terrain (trees never block shots)."""
        try:
            key = (round(a[0], 1), round(a[1], 1), round(a[2], 1), round(b[0], 1), round(b[1], 1), round(b[2], 1), 0)
            r = self._los_cache.get(key)
            if r is None:
                r = not self._seg_blocked(a, b, trees=False)
                self._los_cache[key] = r
            return r
        except Exception:
            return True

    def los(self, a: Vec3, b: Vec3) -> bool:
        """Sight line a->b clear of buildings, terrain, trunks and dense canopy (vision rules, §8)."""
        try:
            key = (round(a[0], 1), round(a[1], 1), round(a[2], 1), round(b[0], 1), round(b[1], 1), round(b[2], 1), 1)
            r = self._los_cache.get(key)
            if r is None:
                r = not self._seg_blocked(a, b, trees=True)
                self._los_cache[key] = r
            return r
        except Exception:
            return True

    def shot_clear_many(self, a: Vec3, pts: Sequence[Vec3]) -> List[bool]:
        """shot_clear from one origin to many points (shares cell gathering)."""
        return [self.shot_clear(a, p) for p in pts]

    def los_many(self, a: Vec3, pts: Sequence[Vec3]) -> List[bool]:
        return [self.los(a, p) for p in pts]

    # ---- mech-level helpers
    def can_see(self, obs_feet: Vec3, tgt_feet: Vec3, obs_cubes=0, tgt_cubes=0, tgt_height=9.0) -> bool:
        """Vision rule: observer eye -> target centre or top (trees count)."""
        so, stg = size_scale(obs_cubes), size_scale(tgt_cubes)
        eye = (obs_feet[0], obs_feet[1], obs_feet[2] + 8.0 * so)
        h = tgt_height * stg
        return (self.los(eye, (tgt_feet[0], tgt_feet[1], tgt_feet[2] + 0.5 * h))
                or self.los(eye, (tgt_feet[0], tgt_feet[1], tgt_feet[2] + h)))

    def can_shoot(self, shooter_feet: Vec3, tgt_feet: Vec3, shooter_cubes=0, tgt_cubes=0) -> Optional[Vec3]:
        """Best clear aim point on a target mech's body from the shooter's muzzle (gun/laser), or None.

        The segment stops at the target cylinder surface so a target hugging a wall still counts."""
        so, stg = size_scale(shooter_cubes), size_scale(tgt_cubes)
        mx, my, mz = shooter_feet[0], shooter_feet[1], shooter_feet[2] + 7.0 * so
        r = 2.5 * stg
        dx, dy = tgt_feet[0] - mx, tgt_feet[1] - my
        d = math.hypot(dx, dy)
        f = max(0.0, (d - r * 0.8) / d) if d > 1e-6 else 0.0
        for hz in (4.5, 7.0, 2.0, 8.5):
            z = tgt_feet[2] + hz * stg
            end = (mx + dx * f, my + dy * f, mz + (z - mz) * f)
            if self.shot_clear((mx, my, mz), end):
                return (tgt_feet[0], tgt_feet[1], z)
        return None

    # ------------------------------------------------------------------ walkability
    def size_class(self, cubes: float = 0) -> int:
        if not self.ok_nav:
            return 0
        need = 2.5 * size_scale(cubes) + 0.25
        for k, rp in enumerate(self.r_plan):
            if rp >= need:
                return k
        return self.K - 1

    def walkable(self, x, y, k=0) -> bool:
        if not self.ok_nav:
            return True
        return bool((self._Wb[self._vidx(x, y)] >> k) & 1)

    def clearance(self, x, y) -> float:
        """Distance (m, capped 8) from (x, y) to the nearest wall for a mech standing at the ground surface."""
        if not self.ok_nav:
            return 8.0
        return self._DWb[self._vidx(x, y)] / 10.0

    def surface(self, x, y) -> float:
        """Baked ground-column surface (roof top inside buildings, deck on low bridges, else terrain)."""
        if not self.ok_nav:
            return self.height(x, y)
        v = self._vidx(x, y)
        if self._Kb[v] & 15 == 0:
            return self.height(x, y)
        return self._Gl[v]

    def standable(self, x, y, k=0) -> bool:
        """On any sizeable walkable component (ground, roofs, stadium bowl/stands) for class k."""
        if not self.ok_nav:
            return True
        return bool((self._Wb[self._vidx(x, y)] >> (k + 3)) & 1)

    def walk_line(self, x0, y0, x1, y1, k=0, step=0.5, main=False) -> bool:
        """Straight walk (x0,y0)->(x1,y1) stays on standable ground of class k (main component only if
        main=True), never rising more than step_up between samples (drops are allowed). Vectorised, ~20 us."""
        if not self.ok_nav:
            return True
        L = math.hypot(x1 - x0, y1 - y0)
        n = int(L / step) + 2
        sh = k if main else k + 3
        if n <= 40:
            # short line: plain Python over bytes/array (no numpy call overhead)
            Wb, Gl, nx, ny = self._Wb, self._Gl, self.nx, self.ny
            fx0, fy0 = (x0 - self.x0) / self.step, (y0 - self.y0) / self.step
            dfx, dfy = (x1 - x0) / self.step / (n - 1), (y1 - y0) / self.step / (n - 1)
            prev = None
            for q in range(n):
                i = int(fx0 + dfx * q + 0.5)
                j = int(fy0 + dfy * q + 0.5)
                if i < 0 or j < 0 or i >= nx or j >= ny:
                    return False
                v = j * nx + i
                if not (Wb[v] >> sh) & 1:
                    return False
                gz = Gl[v]
                if prev is not None and gz - prev > STEP_UP:
                    return False
                prev = gz
            return True
        t = np.arange(n) * (1.0 / (n - 1))
        i = np.rint((x0 + (x1 - x0) * t - self.x0) / self.step).astype(np.int32)
        j = np.rint((y0 + (y1 - y0) * t - self.y0) / self.step).astype(np.int32)
        if i.min() < 0 or j.min() < 0 or i.max() >= self.nx or j.max() >= self.ny:
            return False
        if not ((self.WALK[j, i] >> sh) & 1).all():
            return False
        g = self.G[j, i]
        return bool((np.diff(g) <= STEP_UP).all())

    # ------------------------------------------------------------------ lattice graph
    def _node_xy(self, n, k):
        xs, ys = self.NXY[k]
        return xs[n], ys[n]

    def node_z(self, n, k=0) -> float:
        xs, ys = self.NXY[k]
        return self.surface(xs[n], ys[n])

    def snap(self, x, y, k=0, max_r=3, need_line=True, z=None) -> int:
        """Nearest lattice node (id) to (x, y[, z]) for class k, -1 if none within max_r blocks.
        With z, nodes on another level (roof vs street) are heavily penalised."""
        if not self.ok_nav:
            return -1
        B = self.block
        bi = int((x - self.x0) / self.step) // B
        bj = int((y - self.y0) / self.step) // B
        off = self.node_off[k]
        xs, ys = self.NXY[k]
        best, bd = -1, 1e18
        fallback, fd = -1, 1e18
        for r in range(0, max_r + 1):
            for dj in range(-r, r + 1):
                for di in range(-r, r + 1):
                    if max(abs(di), abs(dj)) != r:
                        continue
                    i, j = bi + di, bj + dj
                    if not (0 <= i < self.BX and 0 <= j < self.BY):
                        continue
                    n = j * self.BX + i
                    if off[n] == 255:
                        continue
                    d = (xs[n] - x) ** 2 + (ys[n] - y) ** 2
                    if z is not None:
                        dz = abs(self.surface(xs[n], ys[n]) - z)
                        if dz > 2.0:
                            d += 400.0 + 25.0 * dz * dz
                    if d < fd:
                        fallback, fd = n, d
                    if d < bd and (not need_line or self.walk_line(x, y, xs[n], ys[n], k)):
                        best, bd = n, d
            if best >= 0 and r >= 1:
                break
        return best if best >= 0 else fallback

    @staticmethod
    def jet_energy(climb: float) -> float:
        """Energy to climb `climb` metres: jump (free ~2.75 m) then jet at ~8.9 m/s for 15 energy/s.
        Theory 1.7/m; replay house bots used ~2.4/m; plan with 2.0/m + 6 reserve."""
        return 2.0 * max(0.0, climb - 2.0) + 6.0

    @staticmethod
    def jet_cap(energy: float) -> float:
        """Largest climb (m) affordable with `energy`, bucketed (0, 8, 16, 25, 40) so searches are shared."""
        c = max(0.0, (energy - 6.0) / 2.0 + 2.0)
        for b in (40.0, 25.0, 16.0, 8.0):
            if c >= b:
                return b
        return 0.0

    def _search(self, s: _Search, start: int, budget_s: float) -> bool:
        """Advance reverse search toward `start`. True when start is closed (path known)."""
        if start in s.closed:
            return True
        if s.done_fail:
            return False
        k = s.k
        xs, ys = self.NXY[k]
        em = self.emask[k]
        jm = self.jmask[k]
        jc = self.jclimb[k]
        cap4 = s.cap * 4.0
        pen = self.NPEN[k]
        DOFF, DLEN, JOFF, JLEN = self.DOFF, self.DLEN, self.JOFF, self.JLEN
        nj = len(JOFF)
        W = self.W_ASTAR
        NN = len(em)
        sx, sy = xs[start], ys[start]
        t_end = time.perf_counter() + budget_s
        if s.target != start and (len(s.open) < 6000 or
                                  math.hypot(xs[s.target] - sx, ys[s.target] - sy) > 40.0):
            # the start moved: re-target the heuristic (small open lists only, or a big move)
            s.target = start
            s.open = [(s.g[n] + W * math.hypot(xs[n] - sx, ys[n] - sy), n) for (_, n) in s.open if n not in s.closed]
            heapq.heapify(s.open)
        if not s.open and not s.closed:
            n = s.goal
            s.open = [(W * math.hypot(xs[n] - sx, ys[n] - sy), n)]
        g, parent, closed, op = s.g, s.parent, s.closed, s.open
        push, pop = heapq.heappush, heapq.heappop
        cnt = 0
        JF, JM = self.JET_FIXED, self.JET_PER_M
        avoid = s.avoid
        expo = self._expo_pen
        while op:
            f, n = pop(op)
            if n in closed:
                continue
            closed.add(n)
            s.expanded += 1
            if n == start:
                return True
            gn = g[n]
            cnt += 1
            if cnt & 15 == 0 and time.perf_counter() > t_end:
                push(op, (f, n))
                closed.discard(n)
                return False
            # reverse search: incoming walk edges m -> n are bit REV[d] at m = n + DOFF[d]
            for d in range(8):
                m = n + DOFF[d]
                if m < 0 or m >= NN or not (em[m] >> REV[d]) & 1 or m in closed:
                    continue
                gm = gn + DLEN[d] + pen[m]
                if avoid:
                    gm += expo(s, m, xs[m], ys[m]) * DLEN[d]
                if gm < g.get(m, 1e18):
                    g[m] = gm
                    parent[m] = n
                    push(op, (gm + W * math.hypot(xs[m] - sx, ys[m] - sy), m))
            if cap4 > 0:
                # incoming jet edges: m = n - JOFF[d] has bit d
                for d in range(nj):
                    m = n - JOFF[d]
                    if m < 0 or m >= NN or not (jm[m] >> d) & 1 or m in closed:
                        continue
                    c4 = jc[m * nj + d]
                    if c4 > cap4:
                        continue
                    gm = gn + JLEN[d] + JF + JM * c4 * 0.25 + pen[m]
                    if avoid:
                        gm += expo(s, m, xs[m], ys[m]) * JLEN[d]
                    if gm < g.get(m, 1e18):
                        g[m] = gm
                        parent[m] = n
                        push(op, (gm + W * math.hypot(xs[m] - sx, ys[m] - sy), m))
        s.done_fail = True
        return False

    def _get_search(self, goal: int, k: int, start: int, cap: float, avoid=()) -> _Search:
        akey = tuple(sorted((int(a[0] // 10), int(a[1] // 10)) for a in avoid))
        key = (goal, k, cap, akey)
        s = self._searches.get(key)
        if s is None:
            if len(self._searches) >= self.MAX_SEARCHES:
                old = min(self._searches.items(), key=lambda kv: kv[1].t_last)[0]
                del self._searches[old]
            s = _Search(goal, k, start)
            s.cap = cap
            s.avoid = tuple((float(a[0]), float(a[1]), float(a[2]) if len(a) > 2 else self.surface(a[0], a[1]))
                            for a in avoid)
            self._searches[key] = s
        s.t_last = time.perf_counter()
        return s

    def edge_kind(self, a: int, b: int, k=0):
        """('walk', 0) or ('jet', climb_m) for consecutive path nodes a -> b."""
        dd = b - a
        d = self._dmap.get(dd)
        if d is not None and (self.emask[k][a] >> d) & 1:
            return ("walk", 0.0)
        d = self._jmap.get(dd)
        if d is not None and (self.jmask[k][a] >> d) & 1:
            return ("jet", self.jclimb[k][a * len(self.JOFF) + d] * 0.25)
        return ("walk", 0.0)

    EXPO_COST = 1.5            # extra cost per metre walked on nodes a threat can see (x threats, capped 2)
    EXPO_RANGE = 200.0

    def _expo_pen(self, s: _Search, m: int, x: float, y: float) -> float:
        v = s.expo.get(m)
        if v is None:
            v = 0.0
            for t in s.avoid:
                d = math.hypot(x - t[0], y - t[1])
                if d < self.EXPO_RANGE:
                    buf = self.shadow(t, self.EXPO_RANGE)
                    if not self.hidden_by_shadow(buf, t, ((x, y),), 1.5)[0]:
                        v += self.EXPO_COST * (1.0 if d > 60.0 else 1.5)
            v = min(v, 2.0 * self.EXPO_COST)
            s.expo[m] = v
        return v

    def plan_nodes(self, start: Vec3, goal: Vec3, k=0, budget_ms=3.0, jet_cap=40.0, avoid=()):
        """(status, node list start..goal). status: 'ok' | 'pending' | 'fail' | 'nonav'."""
        if not self.ok_nav:
            return "nonav", []
        sz = float(start[2]) if len(start) > 2 else None
        gz = float(goal[2]) if len(goal) > 2 else None
        sn = self.snap(start[0], start[1], k, max_r=3, z=sz)
        gn = self.snap(goal[0], goal[1], k, max_r=6, need_line=False, z=gz)
        if sn < 0 or gn < 0:
            return "fail", []
        gx, gy = self._node_xy(gn, k)
        self.last_goal_snapped = math.hypot(gx - goal[0], gy - goal[1]) < 4.0
        if sn == gn:
            return "ok", [sn]
        s = self._get_search(gn, k, sn, float(jet_cap), avoid)
        if not self._search(s, sn, budget_ms / 1000.0):
            return ("fail" if s.done_fail else "pending"), []
        out = [sn]
        n = sn
        par = s.parent
        while n != gn and len(out) < 5000:
            n = par[n]
            if n < 0:
                break
            out.append(n)
        return "ok", out

    def smooth(self, x0, y0, nodes: List[int], k=0, max_checks=80, t_end=None) -> List[Tuple[float, float]]:
        """String-pull a walk-only node path from (x0, y0) with walk-line checks (2D waypoints excl. start).
        Past max_checks or the t_end deadline the remaining nodes are returned raw (navigate shortcuts them
        on the fly and the periodic replan smooths them later)."""
        xs, ys = self.NXY[k]
        nz = self.NZ[k]
        pts = [(xs[n], ys[n], nz[n]) for n in nodes]
        if not pts:
            return []
        out = []
        ax, ay = x0, y0
        i = 0
        n = len(pts)
        checks = 0
        while i < n:
            if checks >= max_checks or (t_end is not None and time.perf_counter() > t_end):
                out.extend(pts[i:])
                break
            hi = min(n - 1, i + 12)
            if self.walk_line(ax, ay, pts[hi][0], pts[hi][1], k):
                j = hi
                checks += 1
            else:
                checks += 1
                j = i
                a, b = i, hi - 1
                while a <= b and checks < max_checks:
                    mid = (a + b) // 2
                    checks += 1
                    if self.walk_line(ax, ay, pts[mid][0], pts[mid][1], k):
                        j = mid
                        a = mid + 1
                    else:
                        b = mid - 1
            out.append(pts[j])
            ax, ay = pts[j][0], pts[j][1]
            i = j + 1
        return out

    def plan_full(self, start: Vec3, goal: Vec3, cubes: float = 0, budget_ms: float = 3.0, jet_cap: float = 40.0,
                  smooth_ms: float = 1.0, avoid=()):
        """(status, waypoints) with waypoints [(x, y, z, act, climb)], act 'walk' or 'jet' (the hop that
        ARRIVES at this waypoint is a jump+jet of `climb` metres from the previous waypoint)."""
        if not self.ok_nav:
            return "nonav", [(float(goal[0]), float(goal[1]), float(goal[2]) if len(goal) > 2 else 0.0, "walk", 0.0)]
        k = self.size_class(cubes)
        st, nodes = self.plan_nodes(start, goal, k, budget_ms, jet_cap, avoid=avoid)
        if st != "ok":
            self.last_raw_path = []
            return st, []
        xs, ys = self.NXY[k]
        self.last_raw_path = [(xs[n], ys[n]) for n in nodes]
        t_sm = time.perf_counter() + smooth_ms / 1000.0
        # split into walk runs at jet edges
        out = []
        run = [nodes[0]]
        ax, ay = float(start[0]), float(start[1])
        for a, b in zip(nodes, nodes[1:]):
            kind, climb = self.edge_kind(a, b, k)
            if kind == "jet":
                for (x, y, z) in self.smooth(ax, ay, run, k, max_checks=40, t_end=t_sm):
                    out.append((x, y, z, "walk", 0.0))
                bx_, by_ = xs[b], ys[b]
                out.append((bx_, by_, self.NZ[k][b], "jet", climb))
                ax, ay = bx_, by_
                run = [b]
            else:
                run.append(b)
        for (x, y, z) in self.smooth(ax, ay, run, k, max_checks=60, t_end=t_sm):
            out.append((x, y, z, "walk", 0.0))
        gx, gy = float(goal[0]), float(goal[1])
        gz = float(goal[2]) if len(goal) > 2 else self.surface(gx, gy)
        if out and math.hypot(out[-1][0] - gx, out[-1][1] - gy) > 0.5:
            if self.walk_line(out[-1][0], out[-1][1], gx, gy, k) or not self.last_goal_snapped:
                out.append((gx, gy, gz, "walk", 0.0))
        elif out:
            out[-1] = (gx, gy, gz, out[-1][3], out[-1][4])
        # drop a leading waypoint we can bypass on foot
        if len(out) >= 2 and out[0][3] == "walk" and out[1][3] == "walk" and \
                self.walk_line(start[0], start[1], out[1][0], out[1][1], k):
            out = out[1:]
        if not out:
            out = [(gx, gy, gz, "walk", 0.0)]
        return "ok", out

    def plan(self, start: Vec3, goal: Vec3, cubes: float = 0, budget_ms: float = 3.0,
             jet_cap: float = 40.0) -> List[Vec3]:
        """Walkable waypoints from start to goal (excluding start, including goal). [] if unreachable.

        Jet hops are included as plain waypoints (use plan_full for the hop types). If the search has not
        finished within budget_ms, returns [goal] (straight line) and keeps the search state: calling again
        (any start nearby) continues it."""
        t0 = time.perf_counter()
        self.stats["plan_calls"] += 1
        try:
            st, wps = self.plan_full(start, goal, cubes, budget_ms, jet_cap)
            if st == "fail":
                return []
            if st == "pending":
                return [tuple(goal)]
            return [(w[0], w[1], w[2]) for w in wps]
        except Exception as e:
            _log("plan error", repr(e))
            return [tuple(goal)]
        finally:
            dt = (time.perf_counter() - t0) * 1000
            if dt > self.stats["plan_ms_max"]:
                self.stats["plan_ms_max"] = dt

    def path_len(self, start: Vec3, goal: Vec3, cubes: float = 0, budget_ms: float = 2.0,
                 jet_cap: float = 40.0) -> float:
        """Length (m) along the planned path, jet hops counted at their horizontal length plus 2x the climb;
        math.inf if unreachable. While the search is still pending, returns 1.35 x straight line."""
        d = math.hypot(goal[0] - start[0], goal[1] - start[1])
        if not self.ok_nav:
            return d
        try:
            k = self.size_class(cubes)
            st, nodes = self.plan_nodes(start, goal, k, budget_ms, jet_cap)
            if st == "fail":
                return math.inf
            if st != "ok":
                return d * 1.35
            xs, ys = self.NXY[k]
            L = math.hypot(xs[nodes[0]] - start[0], ys[nodes[0]] - start[1])
            for a, b in zip(nodes, nodes[1:]):
                L += math.hypot(xs[b] - xs[a], ys[b] - ys[a])
                if (b - a) not in self._DOFFSET:
                    L += 2.0 * self.edge_kind(a, b, k)[1]
            L += math.hypot(goal[0] - xs[nodes[-1]], goal[1] - ys[nodes[-1]])
            return L * 0.97   # lattice paths are slightly longer than smoothed ones
        except Exception:
            return d * 1.35

    # ------------------------------------------------------------------ travel-time field (zone)
    def zone_field(self, cx: float, cy: float, r: float, cubes: float = 0) -> "_Flood":
        """Field of walking distance (m) from every lattice node to the circle (cx, cy, r): multi-source reverse
        Dijkstra, advanced in slices with flood_advance(). Cached (2 most recent circles)."""
        k = self.size_class(cubes)
        key = (round(cx), round(cy), round(r), k)
        f = self._floods.get(key)
        if f is None:
            if len(self._floods) >= 2:
                del self._floods[min(self._floods, key=lambda q: self._floods[q].t_used)]
            f = _Flood(k, float(cx), float(cy), float(r))
            self._floods[key] = f
        f.t_used = time.perf_counter()
        return f

    def flood_advance(self, f: "_Flood", budget_ms: float = 0.7) -> bool:
        """Work on the field for up to budget_ms. True when complete."""
        if f.done or not self.ok_nav:
            return True
        t_end = time.perf_counter() + budget_ms / 1000.0
        k = f.k
        xs, ys = self.NXY[k]
        off = self.node_off[k]
        B = self.block
        if not f.init_done:
            # sources: nodes inside the circle within a 12 m band of its edge (interior nodes are 0 by definition)
            bi0 = max(0, int((f.cx - f.r - self.x0) / self.step) // B - 1)
            bi1 = min(self.BX - 1, int((f.cx + f.r - self.x0) / self.step) // B + 1)
            bj0 = max(0, int((f.cy - f.r - self.y0) / self.step) // B - 1)
            bj1 = min(self.BY - 1, int((f.cy + f.r - self.y0) / self.step) // B + 1)
            if f.scan is None:
                f.scan = bj0
            band = max(0.0, f.r - 12.0)
            while f.scan <= bj1:
                j = f.scan
                for i in range(bi0, bi1 + 1):
                    n = j * self.BX + i
                    if off[n] == 255:
                        continue
                    d = math.hypot(xs[n] - f.cx, ys[n] - f.cy)
                    if band <= d <= f.r:
                        f.dist[n] = 0.0
                        f.heap.append((0.0, n))
                f.scan += 1
                if time.perf_counter() > t_end:
                    return False
            heapq.heapify(f.heap)
            f.init_done = True
        em = self.emask[k]
        pen = self.NPEN[k]
        jm, jc = self.jmask[k], self.jclimb[k]
        DOFF, DLEN, JOFF, JLEN = self.DOFF, self.DLEN, self.JOFF, self.JLEN
        nj = len(JOFF)
        NN = len(em)
        JF, JM = self.JET_FIXED, self.JET_PER_M
        dist, closed, heap = f.dist, f.closed, f.heap
        pop, push = heapq.heappop, heapq.heappush
        cnt = 0
        r2 = f.r * f.r
        while heap:
            dn, n = pop(heap)
            if n in closed:
                continue
            closed.add(n)
            cnt += 1
            if dn > f.max_cost:
                continue
            for d in range(8):
                m = n + DOFF[d]
                if m < 0 or m >= NN or m in closed or not (em[m] >> REV[d]) & 1:
                    continue
                if (xs[m] - f.cx) ** 2 + (ys[m] - f.cy) ** 2 <= r2:
                    continue          # inside the circle: 0 by definition, never expanded
                dm = dn + DLEN[d] + pen[m]
                if dm < dist.get(m, 1e18):
                    dist[m] = dm
                    push(heap, (dm, m))
            for d in range(nj):
                m = n - JOFF[d]
                if m < 0 or m >= NN or m in closed or not (jm[m] >> d) & 1:
                    continue
                if (xs[m] - f.cx) ** 2 + (ys[m] - f.cy) ** 2 <= r2:
                    continue
                dm = dn + JLEN[d] + JF + JM * jc[m * nj + d] * 0.25 + pen[m]
                if dm < dist.get(m, 1e18):
                    dist[m] = dm
                    push(heap, (dm, m))
            if cnt & 3 == 0 and time.perf_counter() > t_end:
                return False
        f.done = True
        return True

    def flood_cost(self, f: "_Flood", x: float, y: float, z: Optional[float] = None) -> Optional[float]:
        """Walking metres from (x, y) to the field's circle: 0 inside, None if not settled yet, inf if the
        field is complete and the spot can't reach the circle."""
        if math.hypot(x - f.cx, y - f.cy) <= f.r:
            return 0.0
        if not self.ok_nav:
            return math.hypot(x - f.cx, y - f.cy) - f.r
        n = self.snap(x, y, f.k, max_r=2, need_line=False, z=z)
        if n < 0:
            return None
        xs, ys = self.NXY[f.k]
        if math.hypot(xs[n] - f.cx, ys[n] - f.cy) <= f.r:
            return math.hypot(xs[n] - x, ys[n] - y)
        if n in f.closed:
            c = f.dist.get(n, math.inf)
            if c > f.max_cost:
                return None if c != math.inf else (math.inf if f.done else None)
            return c + math.hypot(xs[n] - x, ys[n] - y)
        return None

    # ------------------------------------------------------------------ tactics
    NBINS = 720                     # shadow buffer: 0.5 deg bins

    def shadow(self, src: Vec3, radius: float = 250.0, min_h: float = 8.0):
        """Angular depth buffer from feet position `src`: for each 0.5 deg bin, the distance to the nearest
        tall solid edge (prism top >= src ground + min_h, base below the eye). Points farther than the buffer
        in their bin are hidden behind a building (terrain and low walls ignored: verify with shot_clear).
        Cached per (rounded src, radius) for the current tick."""
        key = ("shadow", round(src[0]), round(src[1]), round(src[2]), int(radius), min_h)
        hit = self._los_cache.get(key)
        if hit is not None:
            return hit
        sx, sy, sz = float(src[0]), float(src[1]), float(src[2])
        gi0, gj0 = self._cell_ij(sx - radius, sy - radius)
        gi1, gj1 = self._cell_ij(sx + radius, sy + radius)
        parts = []
        ce = self.cell_edges
        zthr = sz + min_h
        for gj in range(max(0, gj0), min(self.GY, gj1 + 1)):
            for gi in range(max(0, gi0), min(self.GX, gi1 + 1)):
                c = gj * self.GX + gi
                if ce[c] is not None and self.cell_maxtop[c] >= zthr:
                    parts.append(ce[c])
        buf = np.full(self.NBINS, 1e9)
        if parts:
            ids = np.unique(np.concatenate(parts))
            ids = ids[(self.ETOP[ids] >= zthr) & (self.EBASE[ids] <= sz + 6.0)]
            if ids.size:
                ax, ay = self.EAX[ids] - sx, self.EAY[ids] - sy
                bx, by = self.EBX[ids] - sx, self.EBY[ids] - sy
                L = np.hypot(bx - ax, by - ay)
                ns = np.maximum(2, np.ceil(L / 0.75).astype(np.int64) + 1)
                rep = np.repeat(np.arange(ids.size), ns)
                off = np.arange(rep.size) - np.repeat(np.cumsum(ns) - ns, ns)
                f = off / np.repeat(ns - 1, ns)
                px = ax[rep] + (bx - ax)[rep] * f
                py = ay[rep] + (by - ay)[rep] * f
                d = np.hypot(px, py)
                keep = d <= radius
                b = ((np.arctan2(py[keep], px[keep]) + math.pi) * (self.NBINS / (2 * math.pi))).astype(np.int64) % self.NBINS
                np.minimum.at(buf, b, d[keep])
                # close 1-bin gaps between samples of near edges
                buf = np.minimum(buf, np.maximum(np.roll(buf, 1), np.roll(buf, -1)))
        self._los_cache[key] = buf
        return buf

    def hidden_by_shadow(self, buf, src: Vec3, pts, body_r: float = 2.5) -> List[bool]:
        """For each feet point: fully behind the shadow buffer (its whole body width), so not visible."""
        out = []
        sx, sy = float(src[0]), float(src[1])
        nb = self.NBINS
        k = nb / (2 * math.pi)
        for p in pts:
            dx, dy = p[0] - sx, p[1] - sy
            d = math.hypot(dx, dy)
            if d < 1.0:
                out.append(False)
                continue
            a = math.atan2(dy, dx) + math.pi
            half = math.atan2(body_r, d) * k
            b0 = int((a * k) - half)
            b1 = int((a * k) + half) + 1
            ok = True
            for b in range(b0, b1 + 1):
                if buf[b % nb] + 1.0 > d:
                    ok = False
                    break
            out.append(ok)
        return out

    def exposure(self, pts, threats, radius: float = 230.0) -> List[int]:
        """Number of threat positions (feet) that are NOT shadowed from each point (cheap exposure map)."""
        counts = [0] * len(pts)
        for tp in threats:
            buf = self.shadow(tp, radius)
            for i, h in enumerate(self.hidden_by_shadow(buf, tp, pts)):
                if not h and math.hypot(pts[i][0] - tp[0], pts[i][1] - tp[1]) <= radius:
                    counts[i] += 1
        return counts

    def _verified_hidden(self, c: Vec3, threats, sc: float) -> bool:
        cx, cy, cz = c
        for tp in threats:
            for src in ((tp[0], tp[1], tp[2] + 7.0), (tp[0], tp[1], tp[2] + 8.0)):
                for hz in (4.5 * sc, 8.6 * sc):
                    if self.shot_clear(src, (cx, cy, cz + hz)):
                        return False
        return True

    def nearest_cover(self, pos: Vec3, threat_pos, max_dist: float = 60.0, cubes: float = 0,
                      budget_ms: float = 3.0) -> Optional[Vec3]:
        """Nearby reachable feet position hidden (shots and sight) from the threat(s), or None.

        threat_pos: one feet position or a list of them. Candidates are same-level lattice nodes within
        max_dist; shadow buffers pre-filter, then the best few are verified exactly."""
        if not threat_pos:
            return None
        threats = [threat_pos] if isinstance(threat_pos[0], (int, float)) else list(threat_pos)[:4]
        t_end = time.perf_counter() + budget_ms / 1000.0
        k = self.size_class(cubes)
        x, y = float(pos[0]), float(pos[1])
        z = float(pos[2]) if len(pos) > 2 else self.surface(x, y)
        sc = size_scale(cubes)
        cands = self._candidate_spots(x, y, max_dist, k, z=z, stride=1 if max_dist <= 40 else 2)
        if not cands:
            return None
        pts = [(c[0], c[1]) for c in cands]
        hidden = [True] * len(cands)
        for tp in threats:
            R = math.hypot(tp[0] - x, tp[1] - y) + max_dist + 5
            buf = self.shadow(tp, min(R, 300.0))
            for i, h in enumerate(self.hidden_by_shadow(buf, tp, pts, 2.5 * sc)):
                if not h:
                    hidden[i] = False
        # score: distance, penalise moving toward the threats
        tx = sum(t[0] for t in threats) / len(threats)
        ty = sum(t[1] for t in threats) / len(threats)
        dthr = math.hypot(tx - x, ty - y) or 1.0
        scored = []
        for i, c in enumerate(cands):
            if not hidden[i]:
                continue
            toward = ((c[0] - x) * (tx - x) + (c[1] - y) * (ty - y)) / dthr
            scored.append((c[2] + 0.8 * max(0.0, toward), c))
        scored.sort()
        for _, c in scored[:8]:
            if time.perf_counter() > t_end:
                break
            cz = self.surface(c[0], c[1])
            if self._verified_hidden((c[0], c[1], cz), threats, sc):
                return (c[0], c[1], cz)
        return None

    def flank_positions(self, pos: Vec3, target: Vec3, rng: float = 60.0, n: int = 4, cubes: float = 0,
                        other_threats=()) -> List[Vec3]:
        """Walkable spots ~rng from `target` with a clear shot at it, off our current bearing (+-50..130 deg),
        preferring low exposure to other threats and short trips. Best first."""
        k = self.size_class(cubes)
        tx, ty = float(target[0]), float(target[1])
        tz = float(target[2]) if len(target) > 2 else self.surface(tx, ty)
        base = math.atan2(pos[1] - ty, pos[0] - tx)
        cands = []
        for da in (0.9, -0.9, 1.4, -1.4, 1.9, -1.9, 2.3, -2.3):
            for rr in (rng * 0.8, rng, rng * 1.2):
                a = base + da
                px, py = tx + rr * math.cos(a), ty + rr * math.sin(a)
                if self.walkable(px, py, k) and self.in_bounds(px, py, 3.0):
                    cands.append((px, py))
        if not cands:
            return []
        expo = self.exposure(cands, list(other_threats)) if other_threats else [0] * len(cands)
        sc = size_scale(cubes)
        out = []
        for (px, py), e in sorted(zip(cands, expo), key=lambda q: q[1] * 40 + math.hypot(q[0][0] - pos[0], q[0][1] - pos[1])):
            pz = self.surface(px, py)
            if self.shot_clear((px, py, pz + 7.0 * sc), (tx, ty, tz + 4.5)):
                out.append((px, py, pz))
                if len(out) >= n:
                    break
        return out

    def hold_spots(self, center, radius: float, threats=(), n: int = 5, cubes: float = 0) -> List[Vec3]:
        """Good places to hold inside a circle (final zones): walkable, inside with margin, low exposure to
        known threats, close to walls on several sides (cover to break LOS), not on noise islands."""
        k = self.size_class(cubes)
        cx, cy = float(center[0]), float(center[1])
        R = max(3.0, radius - 4.0)
        cands = [c for c in self._candidate_spots(cx, cy, R, k, stride=1 if R < 40 else 2)
                 if self.walkable(c[0], c[1], k)]
        if not cands:
            return []
        pts = [(c[0], c[1]) for c in cands]
        expo = self.exposure(pts, list(threats)) if threats else [0] * len(pts)
        scored = []
        for (px, py), e in zip(pts, expo):
            # cover richness: walls within ~10 m in several directions
            walls = 0
            for a in range(8):
                ang = a * math.pi / 4
                if not self.walk_line(px, py, px + 9 * math.cos(ang), py + 9 * math.sin(ang), k):
                    walls += 1
            dc = math.hypot(px - cx, py - cy) / max(R, 1.0)
            scored.append((e * 3.0 - min(walls, 4) * 0.7 + dc * 1.5, (px, py, self.surface(px, py))))
        scored.sort(key=lambda q: q[0])
        return [p for _, p in scored[:n]]

    def reach_spot(self, item: Vec3, horiz: float = 3.5, vert: float = 4.0, cubes: float = 0) -> Optional[Vec3]:
        """Nearest standable feet position within `horiz` (horizontal) and `vert` (vertical) of an item, e.g.
        take: 4 / 4 m, cube: 3.5 / 4 m (use a little less). Prefers the main ground component. None if none."""
        if not self.ok_nav:
            return tuple(item)
        k = self.size_class(cubes)
        ix, iy = float(item[0]), float(item[1])
        iz = float(item[2]) if len(item) > 2 else self.surface(ix, iy)
        r = int(math.ceil(horiz))
        best, bd = None, 1e18
        Wb, nx = self._Wb, self.nx
        ci = int(round((ix - self.x0) / self.step))
        cj = int(round((iy - self.y0) / self.step))
        for dj in range(-r, r + 1):
            for di in range(-r, r + 1):
                i, j = ci + di, cj + dj
                if not (0 <= i < self.nx and 0 <= j < self.ny):
                    continue
                x, y = self.x0 + i * self.step, self.y0 + j * self.step
                d = math.hypot(x - ix, y - iy)
                if d > horiz:
                    continue
                v = j * nx + i
                if not (Wb[v] >> (k + 3)) & 1:
                    continue
                z = self.surface(x, y)
                if abs(z - iz) > vert:
                    continue
                score = d - (1.0 if (Wb[v] >> k) & 1 else 0.0)
                if score < bd:
                    best, bd = (x, y, z), score
        return best

    def _candidate_spots(self, x, y, R, k, z=None, stride=1):
        """Lattice nodes within R of (x, y) for class k: (x, y, straight distance); same level as z."""
        if not self.ok_nav:
            out = []
            for a in range(16):
                for r in (10.0, 20.0, 35.0, 50.0):
                    if r <= R:
                        px, py = x + r * math.cos(a * math.pi / 8), y + r * math.sin(a * math.pi / 8)
                        out.append((px, py, r))
            return out
        B = self.block
        bi = int((x - self.x0) / self.step) // B
        bj = int((y - self.y0) / self.step) // B
        rb = int(R / B) + 1
        off = self.node_off[k]
        xs, ys = self.NXY[k]
        nz = self.NZ[k]
        out = []
        for j in range(max(0, bj - rb), min(self.BY, bj + rb + 1), stride):
            for i in range(max(0, bi - rb), min(self.BX, bi + rb + 1), stride):
                n = j * self.BX + i
                if off[n] == 255:
                    continue
                d = math.hypot(xs[n] - x, ys[n] - y)
                if d <= R:
                    if z is not None and abs(nz[n] - z) > 3.0:
                        continue     # other level (roof / pit): not a quick cover spot
                    out.append((xs[n], ys[n], d))
        return out
