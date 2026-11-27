"""Rebuild the 16 workbench PNGs from the approved, opaque 4 x 4 atlas."""

import argparse
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


ICON_NAMES = (
    "inspect_asset", "warn_zero_area", "warn_zero_edge", "select_vertex",
    "grow_selection", "focus_camera", "rescan_asset", "export_package",
    "scan_folder", "texture_colorspace", "material_slot", "ref_tree",
    "status_pass", "status_fixable", "status_reject", "bridge_lookdev",
)
DESTINATION = Path(__file__).resolve().parents[1] / "Plugins/AssetForge/Resources/Workbench/icons"
ICON_SIZE = 64
PADDING = 8


def remove_matte(cell):
    """Fit each pixel to the background and one of the flat foreground inks."""
    background = ImageStat.Stat(cell).median
    difference = ImageChops.subtract(cell, Image.new("RGB", cell.size, tuple(background)))
    red, green, blue = difference.split()
    magnitude = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    # The supplied matte contains low-amplitude compression noise on both sides of each line.
    bounds = magnitude.point(lambda v: 255 if v > 24 else 0).getbbox()
    if not bounds:
        raise ValueError("Empty atlas cell")
    cell = cell.crop((bounds[0] - 2, bounds[1] - 2, bounds[2] + 2, bounds[3] + 2))
    # Opaque interiors of the neutral outline and (where present) its single colored accent.
    groups = ([], [])
    for rgb in cell.getdata():
        if max(rgb) >= 128:
            groups[max(rgb) - min(rgb) > 40].append(rgb)
    inks = []
    for group in groups:
        if len(group) < 30:
            continue
        swatch = tuple(sorted(channel)[len(group) // 2] for channel in zip(*group))
        direction = tuple(f - b for f, b in zip(swatch, background))
        inks.append((swatch, direction, sum(d * d for d in direction)))
    if not inks:
        raise ValueError("No opaque foreground ink in atlas cell")

    @lru_cache(maxsize=None)
    def unmatte(rgb):
        delta = tuple(p - b for p, b in zip(rgb, background))
        if max(delta) < 10:
            return (0, 0, 0, 0)
        best_error = float("inf")
        best = (0, 0, 0, 0)
        for ink, direction, norm in inks:
            coverage = sum(v * d for v, d in zip(delta, direction)) / norm
            coverage = max(0.0, min(1.0, coverage))
            error = sum((v - coverage * d) ** 2 for v, d in zip(delta, direction))
            if error < best_error:
                best_error = error
                best = (*ink, round(255 * coverage))
        return best

    result = Image.new("RGBA", cell.size)
    result.putdata([unmatte(rgb) for rgb in cell.getdata()])
    return result.crop(result.getchannel("A").getbbox())


def extract_icons(atlas):
    if atlas.width != atlas.height or atlas.width % 4:
        raise ValueError("Expected a square 4 x 4 atlas")
    step = atlas.width // 4
    for index, name in enumerate(ICON_NAMES):
        left, top = index % 4 * step, index // 4 * step
        glyph = remove_matte(atlas.crop((left, top, left + step, top + step)))
        extent = ICON_SIZE - PADDING * 2
        factor = extent / max(glyph.size)
        size = tuple(max(1, round(axis * factor)) for axis in glyph.size)
        glyph = glyph.resize(size, Image.Resampling.LANCZOS)
        icon = Image.new("RGBA", (ICON_SIZE, ICON_SIZE))
        icon.paste(glyph, ((ICON_SIZE - glyph.width) // 2, (ICON_SIZE - glyph.height) // 2))
        yield name, icon


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("atlas", type=Path)
    parser.add_argument("--output", type=Path, default=DESTINATION)
    args = parser.parse_args()
    with Image.open(args.atlas) as source:
        icons = list(extract_icons(source.convert("RGB")))
    args.output.mkdir(parents=True, exist_ok=True)
    for name, icon in icons:
        icon.save(args.output / (name + ".png"), optimize=True)


if __name__ == "__main__":
    main()