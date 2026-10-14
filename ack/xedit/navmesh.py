"""Read a plugin's navmeshes through xEdit (scripts/navmesh_dump.pas) and summarise them: the bounds of each
navmesh, and the links between navmeshes. Enough to check a Creation Kit generation without opening the CK: that a
new room is covered, or that an area meant to be an island has no navmesh crossing its doorway and no links out."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Navmesh:
    formid: str
    vertices: list = field(default_factory=list)   # (x, y, z)
    edge_links: list = field(default_factory=list)
    door_triangles: list = field(default_factory=list)

    @property
    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        xs, ys, zs = zip(*self.vertices)
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def spans(self, axis: str, value: float, margin: float = 32) -> bool:
        """Whether the navmesh reaches more than margin past the plane axis = value on both sides (axis 'x' or
        'y'). The margin ignores vertices on a wall line: generated navmesh stops a little short of or past it."""
        k = 'xyz'.index(axis)
        return any(v[k] < value - margin for v in self.vertices) and any(v[k] > value + margin for v in self.vertices)

    def covers(self, x0: float, y0: float, x1: float, y1: float) -> int:
        """How many of its vertices lie inside the rectangle."""
        return sum(1 for x, y, _ in self.vertices if x0 <= x <= x1 and y0 <= y <= y1)


def _vertex(text: str) -> tuple[float, float, float]:
    if text.startswith('raw '):
        return struct.unpack('<3f', bytes.fromhex(text[4:].replace(' ', '')))
    return tuple(float(v) for v in text.split()[:3])


def parse(path: str | Path) -> list[Navmesh]:
    meshes: dict[str, Navmesh] = {}
    for line in Path(path).read_text(encoding='utf8', errors='replace').splitlines():
        kind, fid, text = (line.split('\t') + ['', ''])[:3]
        m = meshes.setdefault(fid, Navmesh(fid))
        if kind == 'V':
            m.vertices.append(_vertex(text))
        elif kind == 'E':
            m.edge_links.append(text)
        elif kind == 'D':
            m.door_triangles.append(text)
    return [m for m in meshes.values() if m.vertices]


def summary(meshes: list[Navmesh]) -> str:
    lines = [f'{len(meshes)} navmeshes, {sum(len(m.vertices) for m in meshes)} vertices']
    for m in sorted(meshes, key=lambda m: -len(m.vertices)):
        (x0, y0, z0), (x1, y1, z1) = m.bounds
        lines.append(f'  {m.formid}  {len(m.vertices):5} verts  x {x0:7.0f}..{x1:7.0f}  y {y0:7.0f}..{y1:7.0f}  '
                     f'z {z0:5.0f}..{z1:5.0f}  links {len(m.edge_links)}  doors {len(m.door_triangles)}')
    return '\n'.join(lines)
