"""Read-only campus geometry. Standard library, metres, x east / y north / z up."""
from array import array
import json
import math
from pathlib import Path
import sys


def inside(x, y, ring):
    result = False
    j = len(ring) - 2
    for i in range(0, len(ring), 2):
        ax, ay, bx, by = ring[j], ring[j + 1], ring[i], ring[i + 1]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            result = not result
        j = i
    return result


def edge_distance2(x, y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    f = max(0., min(1., ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy + 1e-12)))
    return (x - ax - f * dx) ** 2 + (y - ay - f * dy) ** 2


class Prism:
    def __init__(self, p):
        self.base, self.top = p['base'], p['top']
        self.ring, self.holes = p['ring'], p.get('holes', [])
        xs, ys = self.ring[::2], self.ring[1::2]
        self.box = min(xs), min(ys), max(xs), max(ys)
        self.edges = []
        for ring in [self.ring, *self.holes]:
            for i in range(0, len(ring), 2):
                j = (i + 2) % len(ring)
                self.edges.append((ring[i], ring[i + 1], ring[j], ring[j + 1]))

    def contains(self, x, y):
        return inside(x, y, self.ring) and not any(inside(x, y, h) for h in self.holes)

    def overlaps(self, x, y, radius):
        a, b, c, d = self.box
        if x < a - radius or x > c + radius or y < b - radius or y > d + radius:
            return False
        return self.contains(x, y) or any(edge_distance2(x, y, *e) < radius * radius for e in self.edges)

    def ray_hits(self, a, b):
        # First clip the segment to the prism's vertical extent; then test its
        # horizontal slice, including courtyard holes. Roofs and bridges count.
        dz = b[2] - a[2]
        if abs(dz) < 1e-9:
            if not self.base <= a[2] <= self.top:
                return False
            lo, hi = 0., 1.
        else:
            t0, t1 = (self.base - a[2]) / dz, (self.top - a[2]) / dz
            lo, hi = max(0., min(t0, t1)), min(1., max(t0, t1))
            if hi < lo:
                return False
        dx, dy = b[0] - a[0], b[1] - a[1]
        x, y = a[0] + dx * lo, a[1] + dy * lo
        ex, ey = a[0] + dx * hi, a[1] + dy * hi
        if self.contains(x, y) or self.contains(ex, ey):
            return True
        sx, sy = ex - x, ey - y
        for ax, ay, bx, by in self.edges:
            vx, vy = bx - ax, by - ay
            den = sx * vy - sy * vx
            if abs(den) < 1e-9:
                continue
            qx, qy = ax - x, ay - y
            t, u = (qx * vy - qy * vx) / den, (qx * sy - qy * sx) / den
            if 0 <= t <= 1 and 0 <= u <= 1:
                return True
        return False


class World:
    CELL = 32.

    def __init__(self, directory):
        root = Path(directory)
        with (root / 'v2/world.json').open() as f:
            raw = json.load(f)
        b, t = raw['bounds'], raw['terrain']
        self.bounds = b['minX'], b['minY'], b['maxX'], b['maxY']
        self.tx, self.ty, self.step = t['minX'], t['minY'], t['step']
        self.nx, self.ny, self.scale = t['nx'], t['ny'], t.get('scale', .01)
        self.terrain = array('h')
        with (root / 'v2' / 'terrain.i16').open('rb') as f:
            self.terrain.fromfile(f, self.nx * self.ny)
        if sys.byteorder != 'little':
            self.terrain.byteswap()
        self.prisms = [Prism(p) for p in raw['prisms']]
        self.cells = {}
        for i, p in enumerate(self.prisms):
            x0, y0, x1, y1 = p.box
            for gx in range(math.floor(x0 / self.CELL), math.floor(x1 / self.CELL) + 1):
                for gy in range(math.floor(y0 / self.CELL), math.floor(y1 / self.CELL) + 1):
                    self.cells.setdefault((gx, gy), []).append(i)

    def ground(self, x, y):
        fx = max(0., min(self.nx - 1.001, (x - self.tx) / self.step))
        fy = max(0., min(self.ny - 1.001, (y - self.ty) / self.step))
        i, j = int(fx), int(fy)
        u, v = fx - i, fy - j
        k = j * self.nx + i
        h = self.terrain
        return ((h[k] * (1 - u) + h[k + 1] * u) * (1 - v)
                + (h[k + self.nx] * (1 - u) + h[k + self.nx + 1] * u) * v) * self.scale

    def nearby(self, x, y, radius):
        ids = set()
        c = self.CELL
        for gx in range(math.floor((x - radius) / c), math.floor((x + radius) / c) + 1):
            for gy in range(math.floor((y - radius) / c), math.floor((y + radius) / c) + 1):
                ids.update(self.cells.get((gx, gy), ()))
        return ids

    def support_height(self, x, y, ceiling):
        """Highest terrain or solid top below a possible landing height."""
        floor = self.ground(x, y)
        for i in self.nearby(x, y, 0.):
            p = self.prisms[i]
            if floor < p.top <= ceiling + .01 and p.contains(x, y):
                floor = p.top
        return floor

    def free(self, x, y, z=None, radius=3., height=9., step_up=1.2):
        x0, y0, x1, y1 = self.bounds
        if not x0 + radius < x < x1 - radius or not y0 + radius < y < y1 - radius:
            return False
        if z is None:
            z = self.ground(x, y)
        for i in self.nearby(x, y, radius):
            p = self.prisms[i]
            if p.top > z + step_up and p.base < z + height - .2 and p.overlaps(x, y, radius):
                return False
        return True

    def travel_clear(self, a, b, radius=3., height=9., elevated=False):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, math.ceil(d))
        previous = self.ground(a[0], a[1])
        for i in range(1, n + 1):
            f = i / n
            x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
            terrain = self.ground(x, y)
            z = max(terrain, a[2]) if elevated else terrain
            if not self.free(x, y, z, radius, height):
                return False
            if not elevated and terrain - previous > max(1.2, d / n * 1.05):
                return False
            previous = terrain
        return True

    def clear_ray(self, a, b):
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        n = max(1, math.ceil(math.hypot(dx, dy) / 12.))
        ids = set()
        for i in range(n + 1):
            f = i / n
            x, y = a[0] + dx * f, a[1] + dy * f
            ids.update(self.cells.get((math.floor(x / self.CELL), math.floor(y / self.CELL)), ()))
            # A narrow diagonal can touch the adjacent bucket between samples.
            if i:
                px, py = a[0] + dx * (i - 1) / n, a[1] + dy * (i - 1) / n
                for gx in range(math.floor(min(px, x) / self.CELL), math.floor(max(px, x) / self.CELL) + 1):
                    for gy in range(math.floor(min(py, y) / self.CELL), math.floor(max(py, y) / self.CELL) + 1):
                        ids.update(self.cells.get((gx, gy), ()))
        if any(self.prisms[i].ray_hits(a, b) for i in ids):
            return False
        n = max(1, math.ceil(math.hypot(dx, dy) / 4.))
        for i in range(1, n):
            f = i / n
            if a[2] + dz * f < self.ground(a[0] + dx * f, a[1] + dy * f) + .15:
                return False
        return True
