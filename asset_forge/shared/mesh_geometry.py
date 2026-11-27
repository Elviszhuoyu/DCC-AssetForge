# -*- coding: utf-8 -*-
"""Read-only checks on each DCC's triangulation of source polygons."""
from __future__ import absolute_import


def zero_area_triangle(a, b, c):
    """Exact zero cross product in object space, with no unit-dependent tolerance."""
    x, y, z = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    u, v, w = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    return y * w == z * v and z * u == x * w and x * v == y * u


def inspect_mesh_triangles(triangles):
    """Each row carries the original polygon, polygon size, and three corner points."""
    faces = {}
    counts = {}
    triangle_count = 0
    for face, size, a, b, c in triangles:
        local_index = counts.get(face, 0)
        counts[face] = local_index + 1
        triangle_count += 1
        if zero_area_triangle(a, b, c):
            row = faces.setdefault(face, {"face_index": face, "polygon_size": size, "triangle_indices": []})
            row["triangle_indices"].append(local_index)
    hits = [faces[index] for index in sorted(faces)]
    return {"triangle_count": triangle_count, "zero_area_count": sum(len(hit["triangle_indices"]) for hit in hits),
            "faces": hits}
