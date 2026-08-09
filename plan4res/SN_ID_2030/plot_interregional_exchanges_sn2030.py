import csv
import math
import sys
from pathlib import Path


BASE_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\Users\DELL\OpenMod4A\plan4res\outputs\Output_Stochastic\SN_ID_2030_v2")
OUT_DIR = BASE_DIR / "results_simul" / "OUT"
INPUT = OUT_DIR / "MeanImportExport.csv"
OUTPUT_SVG = OUT_DIR / "InterregionalNetExchanges.svg"
OUTPUT_CSV = OUT_DIR / "InterregionalNetExchanges.csv"

# Layout chosen for readability, not exact geography.
POSITIONS = {
    "Dakar": (110, 300),
    "Thies": (320, 275),
    "Diourbel": (540, 210),
    "LS": (520, 410),
    "FKK": (760, 390),
    "MTKK": (980, 320),
    "ZS": (1030, 520),
}

REGION_COLORS = {
    "Dakar": "#4E79A7",
    "Thies": "#59A14F",
    "Diourbel": "#F28E2B",
    "LS": "#76B7B2",
    "FKK": "#EDC948",
    "MTKK": "#B07AA1",
    "ZS": "#E15759",
}


def read_exchanges():
    with INPUT.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        links = reader.fieldnames[1:]
        sums = {link: 0.0 for link in links}
        gross_forward = {link: 0.0 for link in links}
        gross_reverse = {link: 0.0 for link in links}
        rows = 0
        for row in reader:
            rows += 1
            for link in links:
                value = float(row[link])
                sums[link] += value
                gross_forward[link] += max(value, 0.0)
                gross_reverse[link] += max(-value, 0.0)

    exchanges = []
    for link in links:
        a, b = link.split(">")
        net_gwh = sums[link] / 1000.0
        forward_gwh = gross_forward[link] / 1000.0
        reverse_gwh = gross_reverse[link] / 1000.0
        if net_gwh >= 0:
            source, target, signed_net = a, b, net_gwh
        else:
            source, target, signed_net = b, a, -net_gwh
        exchanges.append(
            {
                "connection": link,
                "source": source,
                "target": target,
                "net_gwh": signed_net,
                "forward_gwh": forward_gwh,
                "reverse_gwh": reverse_gwh,
                "signed_net_gwh_original_direction": net_gwh,
            }
        )
    exchanges.sort(key=lambda r: r["net_gwh"], reverse=True)
    return rows, exchanges


def write_summary(exchanges):
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "connection",
            "source",
            "target",
            "net_gwh",
            "forward_gwh",
            "reverse_gwh",
            "signed_net_gwh_original_direction",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(exchanges)


def line_offset(x1, y1, x2, y2, offset):
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy) or 1
    nx = -dy / length
    ny = dx / length
    return x1 + nx * offset, y1 + ny * offset, x2 + nx * offset, y2 + ny * offset


def make_svg(exchanges):
    width = 1220
    height = 680
    max_flow = max(e["net_gwh"] for e in exchanges)
    min_width = 2.5
    max_width = 18

    edges = []
    labels = []
    for idx, e in enumerate(sorted(exchanges, key=lambda r: r["net_gwh"])):
        sx, sy = POSITIONS[e["source"]]
        tx, ty = POSITIONS[e["target"]]
        stroke_w = min_width + (e["net_gwh"] / max_flow) * (max_width - min_width)
        x1, y1, x2, y2 = line_offset(sx, sy, tx, ty, 0)
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1
        radius = 34
        x1 += dx / length * radius
        y1 += dy / length * radius
        x2 -= dx / length * radius
        y2 -= dy / length * radius
        color = "#3B82F6" if e["net_gwh"] >= 0 else "#EF4444"
        edges.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="{stroke_w:.2f}" stroke-linecap="round" '
            f'marker-end="url(#arrow)"/>'
        )
        lx = (x1 + x2) / 2
        ly = (y1 + y2) / 2 - 8
        label = f'{e["net_gwh"]:,.0f} GWh'
        box_width = 8 * len(label) + 12
        labels.append(
            f'<rect x="{lx - box_width / 2:.1f}" y="{ly - 17:.1f}" width="{box_width:.1f}" height="22" '
            f'rx="3" fill="#ffffff" stroke="#111827" stroke-width="0.8"/>'
        )
        labels.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="13" '
            f'font-weight="700" fill="#000000">{label}</text>'
        )

    nodes = []
    for region, (x, y) in POSITIONS.items():
        nodes.append(
            f'<circle cx="{x}" cy="{y}" r="32" fill="{REGION_COLORS[region]}" stroke="#111827" stroke-width="1.2"/>'
        )
        nodes.append(
            f'<text x="{x}" y="{y + 5}" text-anchor="middle" font-size="14" font-weight="700" fill="#ffffff">{region}</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#3B82F6"/>
    </marker>
  </defs>
  <g font-family="Arial, sans-serif">
    {''.join(edges)}
    {''.join(labels)}
    {''.join(nodes)}
    <rect x="36" y="36" width="282" height="76" fill="#ffffff" stroke="#d1d5db"/>
    <text x="54" y="62" font-size="15" font-weight="700" fill="#111827">Net annual line flows</text>
    <text x="54" y="86" font-size="13" fill="#374151">Arrow direction: net flow on each interconnection</text>
    <text x="54" y="104" font-size="13" fill="#374151">Line width proportional to GWh</text>
  </g>
</svg>
'''


def main():
    rows, exchanges = read_exchanges()
    write_summary(exchanges)
    OUTPUT_SVG.write_text(make_svg(exchanges), encoding="utf-8")
    print(f"rows={rows}")
    print(f"links={len(exchanges)}")
    print(f"svg={OUTPUT_SVG}")
    print(f"csv={OUTPUT_CSV}")


if __name__ == "__main__":
    main()
