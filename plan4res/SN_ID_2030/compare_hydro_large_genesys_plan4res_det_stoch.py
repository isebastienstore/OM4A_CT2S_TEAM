import csv
from pathlib import Path


DET_DIR = Path(r"C:\Users\DELL\OpenMod4A\plan4res\outputs\Output_Deterministic\SN2030_v2")
STOCH_DIR = Path(r"C:\Users\DELL\OpenMod4A\plan4res\outputs\Output_Stochastic\SN_ID_2030_v2")
OUT_DIR = DET_DIR / "analysis_outputs"
OUT_CSV = OUT_DIR / "hydro_large_genesys_plan4res_det_stoch.csv"
OUT_SVG = OUT_DIR / "hydro_large_genesys_plan4res_det_stoch.svg"

YEAR = "2030"
REGION = "MTKK"
GEN_FUEL = "Power"
PLAN4RES_COL = "Hydro|Reservoir"
TIMESLICE_HOURS = 73
PJ_TO_GWH = 277.77777777777777


def find_output_production(case_dir):
    outputs = case_dir / "GENeSYS-MOD" / "outputs"
    matches = sorted(outputs.glob("output_production*.csv"))
    if not matches:
        raise FileNotFoundError(f"No output_production*.csv found in {outputs}")
    return matches[0]


def is_hydro_large(technology):
    normalized = technology.lower().replace("_", " ").replace("-", " ")
    return "hydro" in normalized and "large" in normalized


def read_genesys(case_dir):
    path = find_output_production(case_dir)
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Year") != YEAR:
                continue
            if row.get("Region") != REGION:
                continue
            if row.get("Fuel") != GEN_FUEL:
                continue
            if row.get("Type") != "Production":
                continue
            if not is_hydro_large(row.get("Technology", "")):
                continue
            value_pj = float(row["Value"])
            rows.append(
                {
                    "timeslice": int(row["Timeslice"]),
                    "genesys_technology": row["Technology"],
                    "genesys_pj": value_pj,
                    "genesys_gwh": value_pj * PJ_TO_GWH,
                }
            )
    if not rows:
        raise ValueError(f"No hydro-large Power production rows found in {path}")
    rows.sort(key=lambda r: r["timeslice"])
    return path, rows


def read_plan4res_generation(case_dir):
    path = case_dir / "results_simul" / "OUT" / f"Generation-{REGION}.csv"
    values = []
    dates = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        date_col = reader.fieldnames[0]
        for row in reader:
            dates.append(row[date_col])
            values.append(float(row[PLAN4RES_COL]))
    return path, dates, values


def aggregate_plan4res_for_timeslices(genesys_rows, dates, values):
    out = []
    for row in genesys_rows:
        idx = row["timeslice"] - 1
        window = values[idx : min(idx + TIMESLICE_HOURS, len(values))]
        out.append(
            {
                "datetime": dates[idx] if 0 <= idx < len(dates) else "",
                "gwh": sum(window) / 1000.0,
            }
        )
    return out


def scale_points(rows, x_key, y_key, width, height, margin, x_min, x_max, y_max):
    plot_w = width - 2 * margin
    plot_h = height - 2 * margin
    pts = []
    for row in rows:
        x = margin + (row[x_key] - x_min) / (x_max - x_min) * plot_w
        y = height - margin - row[y_key] / y_max * plot_h
        pts.append(f"{x:.2f},{y:.2f}")
    return " ".join(pts)


def make_svg(rows):
    width = 1450
    height = 700
    margin = 84
    x_min = min(r["timeslice"] for r in rows)
    x_max = max(r["timeslice"] for r in rows)
    y_max = max(
        max(r["genesys_gwh"] for r in rows),
        max(r["plan4res_det_gwh"] for r in rows),
        max(r["plan4res_stoch_gwh"] for r in rows),
    )
    y_max = ((int(y_max) // 5) + 1) * 5

    grid = []
    for i in range(6):
        val = y_max * i / 5
        y = height - margin - val / y_max * (height - 2 * margin)
        grid.append(f'<line x1="{margin}" y1="{y:.1f}" x2="{width - margin}" y2="{y:.1f}" stroke="#d1d5db" stroke-width="1.1"/>')
        grid.append(f'<text x="{margin - 12}" y="{y + 5:.1f}" text-anchor="end" font-size="15" fill="#111827">{val:.0f}</text>')
    for i in range(6):
        val = x_min + (x_max - x_min) * i / 5
        x = margin + (val - x_min) / (x_max - x_min) * (width - 2 * margin)
        grid.append(f'<line x1="{x:.1f}" y1="{margin}" x2="{x:.1f}" y2="{height - margin}" stroke="#e5e7eb" stroke-width="1"/>')
        grid.append(f'<text x="{x:.1f}" y="{height - margin + 28}" text-anchor="middle" font-size="14" fill="#111827">{val:.0f}</text>')

    genesys = scale_points(rows, "timeslice", "genesys_gwh", width, height, margin, x_min, x_max, y_max)
    det = scale_points(rows, "timeslice", "plan4res_det_gwh", width, height, margin, x_min, x_max, y_max)
    stoch = scale_points(rows, "timeslice", "plan4res_stoch_gwh", width, height, margin, x_min, x_max, y_max)

    legend_x = 104
    legend_y = 108
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <g font-family="Arial, sans-serif">
    {''.join(grid)}
    <polyline fill="none" stroke="#174EA6" stroke-width="3.4" points="{genesys}"/>
    <polyline fill="none" stroke="#D81B00" stroke-width="3.0" points="{det}"/>
    <polyline fill="none" stroke="#008A2E" stroke-width="3.0" points="{stoch}"/>
    <line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#111827" stroke-width="2"/>
    <line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" stroke="#111827" stroke-width="2"/>
    <text x="{width / 2}" y="{height - 20}" text-anchor="middle" font-size="18" font-weight="700" fill="#111827">GENeSYS-MOD timeslice</text>
    <text x="26" y="{height / 2}" transform="rotate(-90 26 {height / 2})" text-anchor="middle" font-size="18" font-weight="700" fill="#111827">Hydro reservoir / hydro large production (GWh per 73h block)</text>
    <rect x="{legend_x - 20}" y="{legend_y - 44}" width="440" height="112" fill="#ffffff" stroke="#111827" stroke-width="1.1"/>
    <text x="{legend_x}" y="{legend_y - 20}" font-size="17" font-weight="700" fill="#111827">Series</text>
    <line x1="{legend_x}" y1="{legend_y + 8}" x2="{legend_x + 58}" y2="{legend_y + 8}" stroke="#174EA6" stroke-width="4"/>
    <text x="{legend_x + 72}" y="{legend_y + 13}" font-size="16" font-weight="600" fill="#111827">GENeSYS-MOD hydro large</text>
    <line x1="{legend_x}" y1="{legend_y + 34}" x2="{legend_x + 58}" y2="{legend_y + 34}" stroke="#D81B00" stroke-width="4"/>
    <text x="{legend_x + 72}" y="{legend_y + 39}" font-size="16" font-weight="600" fill="#111827">plan4res deterministic Hydro|Reservoir</text>
    <line x1="{legend_x}" y1="{legend_y + 60}" x2="{legend_x + 58}" y2="{legend_y + 60}" stroke="#008A2E" stroke-width="4"/>
    <text x="{legend_x + 72}" y="{legend_y + 65}" font-size="16" font-weight="600" fill="#111827">plan4res stochastic mean Hydro|Reservoir</text>
  </g>
</svg>
'''


def main():
    OUT_DIR.mkdir(exist_ok=True)
    genesys_path, genesys_rows = read_genesys(DET_DIR)
    det_path, det_dates, det_values = read_plan4res_generation(DET_DIR)
    stoch_path, stoch_dates, stoch_values = read_plan4res_generation(STOCH_DIR)
    det_agg = aggregate_plan4res_for_timeslices(genesys_rows, det_dates, det_values)
    stoch_agg = aggregate_plan4res_for_timeslices(genesys_rows, stoch_dates, stoch_values)

    rows = []
    for g, d, s in zip(genesys_rows, det_agg, stoch_agg):
        rows.append(
            {
                "timeslice": g["timeslice"],
                "datetime": d["datetime"],
                "genesys_technology": g["genesys_technology"],
                "genesys_gwh": g["genesys_gwh"],
                "plan4res_det_gwh": d["gwh"],
                "plan4res_stoch_gwh": s["gwh"],
                "det_minus_genesys_gwh": d["gwh"] - g["genesys_gwh"],
                "stoch_minus_genesys_gwh": s["gwh"] - g["genesys_gwh"],
            }
        )

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "timeslice",
            "datetime",
            "genesys_technology",
            "genesys_gwh",
            "plan4res_det_gwh",
            "plan4res_stoch_gwh",
            "det_minus_genesys_gwh",
            "stoch_minus_genesys_gwh",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    OUT_SVG.write_text(make_svg(rows), encoding="utf-8")

    print(f"genesys_file={genesys_path}")
    print(f"det_file={det_path}")
    print(f"stoch_file={stoch_path}")
    print(f"technology={rows[0]['genesys_technology']}")
    print(f"rows={len(rows)}")
    print(f"genesys_total_gwh={sum(r['genesys_gwh'] for r in rows):.3f}")
    print(f"plan4res_det_total_gwh={sum(det_values)/1000:.3f}")
    print(f"plan4res_stoch_total_gwh={sum(stoch_values)/1000:.3f}")
    print(f"csv={OUT_CSV}")
    print(f"svg={OUT_SVG}")


if __name__ == "__main__":
    main()
