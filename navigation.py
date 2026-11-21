"""Bounded A* and local steering; work is capped to protect the 50 ms budget."""
import heapq
import math
import time
from array import array
from collections import deque


class Navigator:
    STEP = 5.

    def __init__(self, world):
        self.world = world
        self.x0, self.y0, x1, y1 = world.bounds
        self.nx = int((x1 - self.x0) / self.STEP) + 1
        self.ny = int((y1 - self.y0) / self.STEP) + 1
        self.open = bytearray(self.nx * self.ny)
        self.heights = array('f', [0.]) * len(self.open)
        for j in range(self.ny):
            for i in range(self.nx):
                k = j * self.nx + i
                x, y = self.point(k)
                z = world.ground(x, y)
                self.heights[k] = z
                self.open[k] = world.free(x, y, z, radius=3.8)
        # Terrain contains sharp elevation changes too. Build connected ground
        # regions so a rooftop or a cliff is never mistaken for a walkable route.
        self.edges = bytearray(len(self.open))
        for j in range(self.ny):
            for i in range(self.nx):
                k = j * self.nx + i
                if not self.open[k]:
                    continue
                x, y = self.point(k)
                for di, dj, bit, reverse in ((1,0,1,2),(0,1,4,8)):
                    a, b = i + di, j + dj
                    nk = b * self.nx + a
                    if a >= self.nx or b >= self.ny or not self.open[nk]:
                        continue
                    previous = self.heights[k]
                    valid = True
                    for s in range(1, 6):
                        h = world.ground(x + di * s, y + dj * s)
                        if abs(h - previous) > 1.2:
                            valid = False
                            break
                        previous = h
                    if valid:
                        self.edges[k] |= bit
                        self.edges[nk] |= reverse
        self.components = array('i', [-1]) * len(self.open)
        self.component_sizes = []
        for k in range(len(self.open)):
            if not self.open[k] or self.components[k] >= 0:
                continue
            cid = len(self.component_sizes)
            pending, size = deque([k]), 0
            self.components[k] = cid
            while pending:
                n = pending.popleft()
                size += 1
                for bit, delta in ((1,1),(2,-1),(4,self.nx),(8,-self.nx)):
                    v = n + delta
                    if self.edges[n] & bit and self.components[v] < 0:
                        self.components[v] = cid
                        pending.append(v)
            self.component_sizes.append(size)
        self.path, self.goal, self.planned = [], None, -100.

    def point(self, k):
        return self.x0 + (k % self.nx) * self.STEP, self.y0 + (k // self.nx) * self.STEP

    def cell(self, x, y):
        i = max(0, min(self.nx - 1, round((x - self.x0) / self.STEP)))
        j = max(0, min(self.ny - 1, round((y - self.y0) / self.STEP)))
        return j * self.nx + i

    def nearest(self, x, y, component=None):
        k = self.cell(x, y)
        def acceptable(v):
            return self.open[v] and (component is None or self.components[v] == component)
        if acceptable(k):
            return k
        i, j = k % self.nx, k // self.nx
        best, bd = None, float('inf')
        for r in range(1, 19):
            for a in range(max(0, i - r), min(self.nx, i + r + 1)):
                for b in (j - r, j + r):
                    if 0 <= b < self.ny and acceptable(b * self.nx + a):
                        p = self.point(b * self.nx + a)
                        d = (p[0] - x) ** 2 + (p[1] - y) ** 2
                        if d < bd:
                            bd, best = d, b * self.nx + a
            for b in range(max(0, j - r + 1), min(self.ny, j + r)):
                for a in (i - r, i + r):
                    if 0 <= a < self.nx and acceptable(b * self.nx + a):
                        p = self.point(b * self.nx + a)
                        d = (p[0] - x) ** 2 + (p[1] - y) ** 2
                        if d < bd:
                            bd, best = d, b * self.nx + a
            if best is not None:
                return best
        return None

    def plan(self, pos, goal, now, zone, threats):
        start = self.nearest(*pos[:2])
        end = self.nearest(*goal[:2], component=self.components[start]) if start is not None else None
        self.goal, self.planned = goal[:2], now
        if start is None or end is None:
            self.path = []
            return
        ex, ey = self.point(end)
        frontier, cost, parent = [(0., 0., start)], {start: 0.}, {}
        best, bh = start, float('inf')
        deadline = time.perf_counter() + .007
        count = 0
        while frontier and count < 1900:
            _, g, k = heapq.heappop(frontier)
            if g > cost.get(k, float('inf')) + 1e-6:
                continue
            count += 1
            if count % 64 == 0 and time.perf_counter() > deadline:
                break
            x, y = self.point(k)
            h = math.hypot(x - ex, y - ey)
            if h < bh:
                best, bh = k, h
            if k == end:
                best = k
                break
            i, j = k % self.nx, k // self.nx
            for di, dj in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                a, b = i + di, j + dj
                if not (0 <= a < self.nx and 0 <= b < self.ny):
                    continue
                nk = b * self.nx + a
                if not self.open[nk]:
                    continue
                if self.components[nk] != self.components[start]:
                    continue
                if di and dj and (not self.open[j * self.nx + a] or not self.open[b * self.nx + i]):
                    continue
                if not di and not self.edges[k] & (4 if dj > 0 else 8):
                    continue
                if not dj and not self.edges[k] & (1 if di > 0 else 2):
                    continue
                if di and dj:
                    horizontal = 1 if di > 0 else 2
                    vertical = 4 if dj > 0 else 8
                    if not (self.edges[k] & horizontal and self.edges[k] & vertical and
                            self.edges[j * self.nx + a] & vertical and self.edges[b * self.nx + i] & horizontal):
                        continue
                step = self.STEP * (1.41421356 if di and dj else 1.)
                if abs(self.heights[nk] - self.heights[k]) > step * 1.05:
                    continue
                px, py = self.point(nk)
                risk = 0.
                margin = math.hypot(px - zone['center'][0], py - zone['center'][1]) - zone['radius'] + 6
                if margin > 0:
                    risk += min(12., 1. + zone['dps'] / 25.)
                for tx, ty, weight in threats:
                    d2 = (px - tx) ** 2 + (py - ty) ** 2
                    if d2 < 90 ** 2:
                        risk += weight * 600. / (d2 + 400.)
                ng = g + step * (1 + risk)
                if ng < cost.get(nk, float('inf')):
                    cost[nk], parent[nk] = ng, k
                    heapq.heappush(frontier, (ng + math.hypot(px - ex, py - ey) * 1.05, ng, nk))
        route = []
        while best != start:
            route.append(self.point(best))
            best = parent[best]
        self.path = route[::-1]

    def waypoint(self, pos, goal, now, zone, threats, radius, height):
        world = self.world
        elevated = pos[2] > world.ground(*pos[:2]) + 3.
        d = math.hypot(goal[0] - pos[0], goal[1] - pos[1])
        if d < 100 and world.travel_clear(pos, goal, radius, height, elevated):
            return goal
        moved = self.goal is None or math.dist(goal[:2], self.goal) > 13
        if moved or now - self.planned > 1.2 or not self.path:
            self.plan(pos, goal, now, zone, threats)
        while self.path and math.dist(pos[:2], self.path[0]) < 6.5:
            self.path.pop(0)
        if not self.path:
            return goal
        for p in self.path[min(7, len(self.path)) - 1::-1]:
            if world.travel_clear(pos, p, radius, height, elevated):
                return p
        return self.path[0]
