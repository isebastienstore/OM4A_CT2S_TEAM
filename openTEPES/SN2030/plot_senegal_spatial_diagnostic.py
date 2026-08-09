from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from adjustText import adjust_text
from matplotlib import patheffects
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parent
FIGURES_DIR = ROOT / "figures"
PROCESSED_DIR = FIGURES_DIR / "processed"
NATIONAL_PNG_PATH = FIGURES_DIR / "senegal_spatial_diagnostic.png"
NATIONAL_PDF_PATH = FIGURES_DIR / "senegal_spatial_diagnostic.pdf"
NATIONAL_SVG_PATH = FIGURES_DIR / "senegal_spatial_diagnostic.svg"
DAKAR_THIES_PNG_PATH = (
    FIGURES_DIR / "senegal_spatial_diagnostic_2030_dakar_zoom.png"
)
DAKAR_THIES_PDF_PATH = (
    FIGURES_DIR / "senegal_spatial_diagnostic_2030_dakar_zoom.pdf"
)
DAKAR_THIES_SVG_PATH = (
    FIGURES_DIR / "senegal_spatial_diagnostic_2030_dakar_zoom.svg"
)
TARGET_CRS = "EPSG:32628"
EPS = 1e-9

# Publication output is designed to remain legible when reduced to roughly
# 0.8\textwidth. The canvas retains the original 12.2:8 aspect ratio; only
# physical output size and presentation-scale values are increased.
FIGURE_SCALE = 1.25
FIGURE_SIZE = (12.2 * FIGURE_SCALE, 8.0 * FIGURE_SCALE)
OUTPUT_DPI = 600
FONT_SCALE = 2.0
MARKER_AREA_SCALE = 1.8
LINE_WIDTH_SCALE = 1.45
BORDER_WIDTH_SCALE = 1.5
HALO_WIDTH_SCALE = 1.4
TEXT_BOX_PAD = 0.30


def publication_font_size(base_size: float) -> float:
    """Scale an existing point size consistently for reduced paper figures."""
    return base_size * FONT_SCALE

META_COLUMNS = ("Period", "Scenario", "LoadLevel")

COLORS = {
    "ink": "#202522",
    "muted": "#68716C",
    "region_edge": "#A7ADA9",
    "node": "#7A827E",
    "ens": "#C62828",
    "curtailment": "#00A6C7",
    "loading_low": "#8D9591",
    "loading_medium": "#E58A2F",
    "loading_high": "#D13B3F",
    "loading_critical": "#68131B",
    "candidate": "#515A55",
}

GENERATION_STYLE = {
    "solar": {"label": "Solar PV", "marker": "s", "color": "#E68622"},
    "wind": {"label": "Wind", "marker": "^", "color": "#248A5A"},
    "hydro": {"label": "Hydro", "marker": "D", "color": "#2878B5"},
    "gas": {"label": "Gas", "marker": "o", "color": "#C73E3A"},
    "oil": {"label": "Oil", "marker": "s", "color": "#171A18"},
    "battery": {"label": "Battery", "marker": "p", "color": "#7B4FA3"},
    "other": {"label": "Other", "marker": "h", "color": "#777F7A"},
}


@dataclass(frozen=True)
class CaseFiles:
    regions: Path
    node_locations: Path
    node_zones: Path
    generation: Path
    network: Path
    demand: Path
    generation_energy: Path
    ens: Path
    curtailment: Path
    flow: Path
    generation_investment: Path | None
    network_investment: Path | None
    plant_inventory: Path | None


def normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def short_node(value: Any) -> str:
    return str(value).replace("Senegal States|", "")


def short_zone(value: Any) -> str:
    return str(value).replace("Senegal Zones|", "")


def finite_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def csv_header(path: Path, separator: str = ",") -> set[str]:
    try:
        return set(pd.read_csv(path, sep=separator, nrows=0).columns.astype(str))
    except Exception:
        return set()


def choose_csv(
    candidates: list[Path],
    *,
    required_columns: Iterable[str] = (),
    preferred_tokens: Iterable[str] = (),
    excluded_tokens: Iterable[str] = (),
    optional: bool = False,
) -> Path | None:
    required = set(required_columns)
    preferred = tuple(normalized(token) for token in preferred_tokens)
    excluded = tuple(normalized(token) for token in excluded_tokens)
    scored: list[tuple[int, int, Path]] = []

    for path in candidates:
        name = normalized(path.stem)
        if any(token and token in name for token in excluded):
            continue
        header = csv_header(path)
        if required and not required.issubset(header):
            continue
        score = sum(12 for token in preferred if token and token in name)
        score += sum(2 for column in required if normalized(column) in name)
        score += 2 if path.parent == ROOT else 0
        scored.append((score, -len(path.name), path))

    if not scored:
        if optional:
            return None
        raise FileNotFoundError(
            "No CSV matched required columns "
            f"{sorted(required)} and tokens {list(preferred_tokens)}"
        )

    scored.sort(reverse=True)
    return scored[0][2]


def identify_region_file(json_candidates: list[Path]) -> Path:
    scored: list[tuple[int, Path]] = []
    for path in json_candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        score = 0
        if payload.get("type") == "Topology":
            object_value = next(iter(payload.get("objects", {}).values()), {})
            geometries = object_value.get("geometries", [])
            if len(geometries) == 7:
                score += 30
            if any("NOMREG" in geometry.get("properties", {}) for geometry in geometries):
                score += 20
        elif payload.get("type") == "FeatureCollection":
            features = payload.get("features", [])
            if len(features) == 7:
                score += 30
        name = normalized(path.stem)
        score += 8 if "senegal" in name else 0
        score += 8 if any(token in name for token in ("region", "regroupe")) else 0
        if score:
            scored.append((score, path))
    if not scored:
        raise FileNotFoundError("No seven-region GeoJSON/TopoJSON file was found")
    scored.sort(key=lambda item: (item[0], -len(str(item[1]))), reverse=True)
    return scored[0][1]


def identify_plant_inventory(csv_candidates: list[Path]) -> Path | None:
    required = {"X", "Y", "Name"}
    matches: list[tuple[int, Path]] = []
    for path in csv_candidates:
        header = csv_header(path, separator=";")
        if required.issubset(header):
            score = 10
            name = normalized(path.stem)
            score += 10 if "plant" in name else 0
            score += 4 if "viz" in normalized(path.parent) else 0
            matches.append((score, path))
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][1]


def discover_files(root: Path = ROOT) -> CaseFiles:
    csv_candidates = [
        path
        for path in root.rglob("*.csv")
        if FIGURES_DIR not in path.parents
    ]
    json_candidates = [
        path
        for path in root.rglob("*")
        if path.suffix.lower() in {".json", ".geojson"}
        and FIGURES_DIR not in path.parents
    ]

    node_locations = choose_csv(
        csv_candidates,
        required_columns=("Node", "Latitude", "Longitude"),
        preferred_tokens=("nodelocation", "data"),
        excluded_tokens=("result",),
    )
    node_zones = choose_csv(
        csv_candidates,
        required_columns=("Node", "Zone"),
        preferred_tokens=("nodetozone", "dict"),
    )
    generation = choose_csv(
        csv_candidates,
        required_columns=("Generator", "Node", "Technology", "MaximumPower"),
        preferred_tokens=("datageneration",),
        excluded_tokens=("result",),
    )
    network = choose_csv(
        csv_candidates,
        required_columns=("InitialNode", "FinalNode", "Circuit", "TTC"),
        preferred_tokens=("datanetwork",),
        excluded_tokens=("result",),
    )
    demand = choose_csv(
        csv_candidates,
        required_columns=META_COLUMNS,
        preferred_tokens=("datademand",),
        excluded_tokens=("result", "market", "netdemand"),
    )
    generation_energy = choose_csv(
        csv_candidates,
        required_columns=META_COLUMNS,
        preferred_tokens=("resultgenerationenergy",),
        excluded_tokens=("technology", "curtailment", "outflow", "spillage"),
    )
    ens = choose_csv(
        csv_candidates,
        required_columns=META_COLUMNS,
        preferred_tokens=("resultnetworkens",),
        excluded_tokens=("cost",),
    )
    curtailment = choose_csv(
        csv_candidates,
        required_columns=META_COLUMNS,
        preferred_tokens=("resultgenerationcurtailmentenergy",),
        excluded_tokens=("relative", "technology"),
    )
    flow = choose_csv(
        csv_candidates,
        required_columns=META_COLUMNS,
        preferred_tokens=("resultnetworkflowelecpernode",),
    )
    generation_investment = choose_csv(
        csv_candidates,
        required_columns=("Period",),
        preferred_tokens=("resultgenerationinvestment",),
        excluded_tokens=("perunit", "cost", "technology"),
        optional=True,
    )
    network_investment = choose_csv(
        csv_candidates,
        required_columns=("Period",),
        preferred_tokens=("resultnetworkinvestment",),
        excluded_tokens=("mwkm",),
        optional=True,
    )

    return CaseFiles(
        regions=identify_region_file(json_candidates),
        node_locations=node_locations,
        node_zones=node_zones,
        generation=generation,
        network=network,
        demand=demand,
        generation_energy=generation_energy,
        ens=ens,
        curtailment=curtailment,
        flow=flow,
        generation_investment=generation_investment,
        network_investment=network_investment,
        plant_inventory=identify_plant_inventory(csv_candidates),
    )


def decode_topojson(path: Path) -> gpd.GeoDataFrame:
    topology = json.loads(path.read_text(encoding="utf-8"))
    scale_x, scale_y = topology["transform"]["scale"]
    translate_x, translate_y = topology["transform"]["translate"]
    decoded_arcs: list[list[tuple[float, float]]] = []

    for encoded_arc in topology["arcs"]:
        x = 0
        y = 0
        coordinates: list[tuple[float, float]] = []
        for delta_x, delta_y in encoded_arc:
            x += delta_x
            y += delta_y
            coordinates.append(
                (
                    x * scale_x + translate_x,
                    y * scale_y + translate_y,
                )
            )
        decoded_arcs.append(coordinates)

    def arc_coordinates(index: int) -> list[tuple[float, float]]:
        return (
            decoded_arcs[index]
            if index >= 0
            else list(reversed(decoded_arcs[~index]))
        )

    def stitch(indices: Iterable[int]) -> list[tuple[float, float]]:
        ring: list[tuple[float, float]] = []
        for index in indices:
            arc = arc_coordinates(index)
            ring.extend(arc if not ring else arc[1:])
        return ring

    object_value = next(iter(topology["objects"].values()))
    records: list[dict[str, Any]] = []
    geometries: list[Any] = []

    for geometry in object_value["geometries"]:
        arc_sets = geometry["arcs"]
        if geometry["type"] == "Polygon":
            arc_sets = [arc_sets]
        polygons: list[Polygon] = []
        for polygon_arcs in arc_sets:
            rings = [stitch(ring) for ring in polygon_arcs]
            if not rings or len(rings[0]) < 4:
                continue
            polygon = Polygon(rings[0], holes=rings[1:])
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            if isinstance(polygon, Polygon):
                polygons.append(polygon)
            elif isinstance(polygon, MultiPolygon):
                polygons.extend(list(polygon.geoms))
        merged = unary_union(polygons)
        properties = geometry.get("properties", {})
        records.append(
            {
                "zone": str(properties.get("NOMREG", properties.get("ID", "Zone"))),
                "region_id": str(properties.get("ID", "")),
            }
        )
        geometries.append(merged)

    return gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")


def load_regions(path: Path) -> gpd.GeoDataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") == "Topology":
        return decode_topojson(path)
    regions = gpd.read_file(path)
    name_column = next(
        (
            column
            for column in regions.columns
            if normalized(column) in {"nomreg", "region", "zone", "name"}
        ),
        None,
    )
    if name_column is None:
        regions["zone"] = [f"Zone {index + 1}" for index in range(len(regions))]
    else:
        regions["zone"] = regions[name_column].astype(str)
    return regions[["zone", "geometry"]].to_crs("EPSG:4326")


def load_geodata(files: CaseFiles) -> dict[str, Any]:
    regions = load_regions(files.regions)
    node_frame = pd.read_csv(files.node_locations)
    node_zone_frame = pd.read_csv(files.node_zones)
    nodes = node_frame.merge(node_zone_frame, on="Node", how="left")
    nodes["zone"] = nodes["Zone"].map(short_zone)
    nodes_gdf = gpd.GeoDataFrame(
        nodes,
        geometry=gpd.points_from_xy(nodes["Longitude"], nodes["Latitude"]),
        crs="EPSG:4326",
    )

    if files.plant_inventory:
        plant_inventory = pd.read_csv(files.plant_inventory, sep=";")
        plant_inventory.columns = plant_inventory.columns.str.strip()
        plant_inventory["Name"] = plant_inventory["Name"].astype(str).str.strip()
        plant_inventory["X"] = pd.to_numeric(
            plant_inventory["X"].astype(str).str.strip(), errors="coerce"
        )
        plant_inventory["Y"] = pd.to_numeric(
            plant_inventory["Y"].astype(str).str.strip(), errors="coerce"
        )
        plant_inventory = plant_inventory.dropna(subset=["X", "Y"])
    else:
        plant_inventory = pd.DataFrame(columns=["X", "Y", "Name", "statut"])

    return {
        "regions": regions,
        "nodes": nodes_gdf,
        "plant_inventory": plant_inventory,
    }


def load_network(
    files: CaseFiles,
    nodes: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, dict[tuple[str, str, str], float]]:
    network = pd.read_csv(files.network)
    coordinate_lookup = {
        row.Node: (row.geometry.x, row.geometry.y)
        for row in nodes.itertuples(index=False)
    }
    valid = network["InitialNode"].isin(coordinate_lookup) & network["FinalNode"].isin(
        coordinate_lookup
    )
    if not valid.all():
        missing = network.loc[~valid, ["InitialNode", "FinalNode"]]
        raise ValueError(f"Network nodes without coordinates:\n{missing}")

    geometry = [
        LineString(
            [
                coordinate_lookup[row.InitialNode],
                coordinate_lookup[row.FinalNode],
            ]
        )
        for row in network.itertuples(index=False)
    ]
    network_gdf = gpd.GeoDataFrame(network, geometry=geometry, crs="EPSG:4326")
    flows = pd.read_csv(files.flow, header=[0, 1, 2])
    investments = read_network_investments(files.network_investment)
    return network_gdf, flows, investments


def read_generation_investments(path: Path | None) -> dict[str, float]:
    if path is None:
        return {}
    frame = pd.read_csv(path)
    if frame.empty:
        return {}
    row = frame.iloc[0]
    return {
        str(column): finite_float(row[column])
        for column in frame.columns
        if str(column) != "Period"
    }


def read_network_investments(
    path: Path | None,
) -> dict[tuple[str, str, str], float]:
    if path is None:
        return {}
    frame = pd.read_csv(path, header=[0, 1, 2])
    if frame.empty:
        return {}
    row = frame.iloc[0]
    result: dict[tuple[str, str, str], float] = {}
    for column in frame.columns:
        if str(column[0]) == "Period":
            continue
        result[(str(column[0]), str(column[1]), str(column[2]))] = finite_float(
            row[column]
        )
    return result


def technology_group(technology: Any, storage_type: Any = "") -> str:
    tech = str(technology).lower()
    storage = str(storage_type).lower()
    if "battery" in tech or "bess" in tech or "battery" in storage:
        return "battery"
    if "pv" in tech or "solar" in tech:
        return "solar"
    if "wind" in tech:
        return "wind"
    if "hydro" in tech:
        return "hydro"
    if "gas" in tech:
        return "gas"
    if "oil" in tech or "diesel" in tech:
        return "oil"
    return "other"


def name_fingerprint(value: Any) -> str:
    tokens = re.findall(r"[a-z0-9]+", str(value).lower())
    return "|".join(sorted(tokens))


def locate_generators(
    generation: pd.DataFrame,
    nodes: gpd.GeoDataFrame,
    plant_inventory: pd.DataFrame,
) -> pd.DataFrame:
    node_coordinates = {
        row.Node: (row.geometry.x, row.geometry.y, row.zone)
        for row in nodes.itertuples(index=False)
    }
    inventory = plant_inventory.copy()
    inventory["normalized_name"] = inventory["Name"].map(normalized)
    inventory["fingerprint"] = inventory["Name"].map(name_fingerprint)

    exact_lookup = {
        key: group.iloc[0]
        for key, group in inventory.groupby("normalized_name", sort=False)
    }
    fingerprint_lookup = {
        key: group.iloc[0]
        for key, group in inventory.groupby("fingerprint", sort=False)
        if len(group) == 1
    }

    records: list[dict[str, Any]] = []
    for row in generation.itertuples(index=False):
        generator = str(row.Generator)
        match = exact_lookup.get(normalized(generator))
        if match is None:
            match = fingerprint_lookup.get(name_fingerprint(generator))
        node_lon, node_lat, zone = node_coordinates[str(row.Node)]
        if match is not None:
            longitude = finite_float(match["X"])
            latitude = finite_float(match["Y"])
            coordinate_source = "plant inventory"
        else:
            longitude = node_lon
            latitude = node_lat
            coordinate_source = "model node"
        record = row._asdict()
        record.update(
            {
                "longitude": longitude,
                "latitude": latitude,
                "zone": zone,
                "coordinate_source": coordinate_source,
            }
        )
        records.append(record)

    located = pd.DataFrame(records)
    fallback = located["coordinate_source"].eq("model node")
    for _, group in located[fallback].groupby("Node"):
        if len(group) <= 1:
            continue
        for position, index in enumerate(group.index):
            angle = 2 * math.pi * position / len(group)
            located.at[index, "longitude"] += 0.014 * math.cos(angle)
            located.at[index, "latitude"] += 0.014 * math.sin(angle)
    return located


def load_results(
    files: CaseFiles,
    geodata: dict[str, Any],
) -> dict[str, Any]:
    generation = pd.read_csv(files.generation)
    investments = read_generation_investments(files.generation_investment)
    generation_energy = pd.read_csv(files.generation_energy)
    ens = pd.read_csv(files.ens)
    curtailment = pd.read_csv(files.curtailment)
    demand = pd.read_csv(files.demand)

    year = int(finite_float(generation_energy.iloc[0]["Period"]))
    scenario = str(generation_energy.iloc[0]["Scenario"])
    located = locate_generators(
        generation,
        geodata["nodes"],
        geodata["plant_inventory"],
    )

    annual_generation = (
        generation_energy.drop(columns=list(META_COLUMNS))
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .sum(axis=0)
    )
    located["generation_gwh"] = located["Generator"].map(annual_generation).fillna(0.0)
    located["technology_group"] = [
        technology_group(row.Technology, getattr(row, "StorageType", ""))
        for row in located.itertuples(index=False)
    ]
    located["is_renewable"] = located["Technology"].astype(str).str.startswith("RES_")
    located["is_candidate"] = located["Generator"].isin(investments)

    def installed_capacity(row: pd.Series) -> float:
        generator = str(row["Generator"])
        if generator in investments:
            return investments[generator]
        if finite_float(row["InitialPeriod"]) <= year <= finite_float(row["FinalPeriod"]):
            return finite_float(row["MaximumPower"])
        return 0.0

    located["installed_mw"] = located.apply(installed_capacity, axis=1)
    located["selected_in_2030"] = (~located["is_candidate"]) | (
        located["installed_mw"] > EPS
    )
    generators_gdf = gpd.GeoDataFrame(
        located,
        geometry=gpd.points_from_xy(located["longitude"], located["latitude"]),
        crs="EPSG:4326",
    )

    annual_ens = (
        ens.drop(columns=list(META_COLUMNS))
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .sum(axis=0)
    )
    ens_frame = pd.DataFrame(
        {
            "Node": annual_ens.index.astype(str),
            "ens_gwh": annual_ens.values,
        }
    )
    ens_frame["ens_gwh"] = ens_frame["ens_gwh"].where(
        ens_frame["ens_gwh"].abs() >= EPS, 0.0
    )
    ens_frame["ens_mwh"] = ens_frame["ens_gwh"] * 1000
    ens_gdf = geodata["nodes"][["Node", "zone", "geometry"]].merge(
        ens_frame, on="Node", how="left"
    )
    ens_gdf["ens_gwh"] = ens_gdf["ens_gwh"].fillna(0.0)
    ens_gdf["ens_mwh"] = ens_gdf["ens_mwh"].fillna(0.0)

    annual_curtailment = (
        curtailment.drop(columns=list(META_COLUMNS))
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .sum(axis=0)
    )
    annual_curtailment = annual_curtailment.where(
        annual_curtailment.abs() >= EPS, 0.0
    )
    generator_to_node = generation.set_index("Generator")["Node"]
    curtailment_frame = pd.DataFrame(
        {
            "Generator": annual_curtailment.index.astype(str),
            "curtailment_gwh": annual_curtailment.values,
        }
    )
    curtailment_frame["Node"] = curtailment_frame["Generator"].map(generator_to_node)
    curtailment_by_node = (
        curtailment_frame.groupby("Node", as_index=False)["curtailment_gwh"].sum()
    )
    curtailment_gdf = geodata["nodes"][["Node", "zone", "geometry"]].merge(
        curtailment_by_node, on="Node", how="inner"
    )

    demand_values = (
        demand.drop(columns=list(META_COLUMNS))
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
    )
    total_generation_gwh = finite_float(annual_generation.sum())
    renewable_names = set(
        generation.loc[
            generation["Technology"].astype(str).str.startswith("RES_"), "Generator"
        ].astype(str)
    )
    renewable_generation_gwh = finite_float(
        annual_generation[
            [name for name in annual_generation.index if name in renewable_names]
        ].sum()
    )

    return {
        "year": year,
        "scenario": scenario,
        "generators": generators_gdf,
        "ens": ens_gdf,
        "curtailment": curtailment_gdf,
        "kpis": {
            "scenario": scenario,
            "year": year,
            "renewable_share_pct": (
                100 * renewable_generation_gwh / total_generation_gwh
                if total_generation_gwh
                else 0.0
            ),
            "curtailment_gwh": finite_float(annual_curtailment.sum()),
            "ens_gwh": finite_float(annual_ens.sum()),
            "peak_demand_mw": finite_float(
                demand_values.clip(lower=0.0).sum(axis=1).max()
            ),
            "total_generation_gwh": total_generation_gwh,
        },
    }


def compute_loading(
    network: gpd.GeoDataFrame,
    flows: pd.DataFrame,
    investments: dict[tuple[str, str, str], float],
    year: int,
) -> gpd.GeoDataFrame:
    result = network.copy()
    result["candidate"] = result["FixedInvestmentCost"].notna()
    result["investment_decision"] = [
        investments.get(
            (str(row.InitialNode), str(row.FinalNode), str(row.Circuit)),
            0.0,
        )
        for row in result.itertuples(index=False)
    ]
    result["active_in_year"] = (
        pd.to_numeric(result["InitialPeriod"], errors="coerce").fillna(-np.inf)
        <= year
    ) & (
        pd.to_numeric(result["FinalPeriod"], errors="coerce").fillna(np.inf)
        >= year
    )
    result["max_abs_flow_mw"] = 0.0
    result["p95_abs_flow_mw"] = 0.0
    result["mean_abs_flow_mw"] = 0.0
    result["max_loading_pct"] = 0.0
    result["p95_loading_pct"] = 0.0
    result["peak_load_level"] = ""

    flow_values = flows.iloc[:, 3:].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    load_levels = flows.iloc[:, 2].astype(str)
    flow_lookup = {
        (str(column[0]), str(column[1]), str(column[2])): position
        for position, column in enumerate(flow_values.columns)
    }

    for index, row in result.iterrows():
        key = (str(row["InitialNode"]), str(row["FinalNode"]), str(row["Circuit"]))
        position = flow_lookup.get(key)
        if position is None:
            continue
        series = flow_values.iloc[:, position].abs()
        security_factor = finite_float(row.get("SecurityFactor"), 1.0)
        if security_factor <= 0:
            security_factor = 1.0
        available_capacity = finite_float(row.get("TTC")) * security_factor
        maximum = finite_float(series.max())
        p95 = finite_float(series.quantile(0.95))
        result.at[index, "max_abs_flow_mw"] = maximum
        result.at[index, "p95_abs_flow_mw"] = p95
        result.at[index, "mean_abs_flow_mw"] = finite_float(series.mean())
        if available_capacity > 0:
            result.at[index, "max_loading_pct"] = 100 * maximum / available_capacity
            result.at[index, "p95_loading_pct"] = 100 * p95 / available_capacity
        if maximum > 0:
            result.at[index, "peak_load_level"] = load_levels.iloc[int(series.argmax())]

    maximum_p95 = max(finite_float(result["p95_abs_flow_mw"].max()), 1.0)
    result["plot_width"] = 0.55 + 2.7 * np.sqrt(
        result["p95_abs_flow_mw"].clip(lower=0.0) / maximum_p95
    )

    def loading_style(value: float) -> tuple[str, str]:
        if value < 50:
            return "0-50%", COLORS["loading_low"]
        if value < 80:
            return "50-80%", COLORS["loading_medium"]
        if value < 95:
            return "80-95%", COLORS["loading_high"]
        return ">=95%", COLORS["loading_critical"]

    styles = result["max_loading_pct"].map(loading_style)
    result["loading_class"] = [value[0] for value in styles]
    result["plot_color"] = [value[1] for value in styles]
    result["corridor_name"] = (
        result["InitialNode"].map(short_node)
        + " - "
        + result["FinalNode"].map(short_node)
        + " ("
        + result["Circuit"].astype(str)
        + ")"
    )
    return result


def offset_parallel_lines(lines: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    shifted = lines.copy()
    shifted["corridor_key"] = [
        "||".join(sorted((str(row.InitialNode), str(row.FinalNode))))
        for row in shifted.itertuples(index=False)
    ]
    for _, group in shifted.groupby("corridor_key", sort=False):
        if len(group) <= 1:
            continue
        ordered_indices = list(group.sort_values("Circuit").index)
        for position, index in enumerate(ordered_indices):
            geometry = shifted.at[index, "geometry"]
            start = geometry.coords[0]
            end = geometry.coords[-1]
            delta_x = end[0] - start[0]
            delta_y = end[1] - start[1]
            length = math.hypot(delta_x, delta_y)
            if length == 0:
                continue
            normal_x = -delta_y / length
            normal_y = delta_x / length
            centered = position - (len(ordered_indices) - 1) / 2
            distance = centered * 650.0
            shifted.at[index, "geometry"] = affinity.translate(
                geometry,
                xoff=normal_x * distance,
                yoff=normal_y * distance,
            )
    return shifted.drop(columns="corridor_key")


def plot_regions(ax: plt.Axes, regions: gpd.GeoDataFrame) -> None:
    regions.plot(
        ax=ax,
        facecolor="#FFFFFF",
        edgecolor=COLORS["region_edge"],
        linewidth=0.78 * LINE_WIDTH_SCALE,
        zorder=1,
    )
    effects = [
        patheffects.withStroke(
            linewidth=2.8 * HALO_WIDTH_SCALE,
            foreground="white",
            alpha=0.94,
        )
    ]
    for row in regions.itertuples(index=False):
        point = row.geometry.representative_point()
        ax.text(
            point.x,
            point.y,
            str(row.zone).upper(),
            ha="center",
            va="center",
            fontsize=publication_font_size(8.2),
            color="#737B77",
            fontweight="bold",
            path_effects=effects,
            clip_on=True,
            zorder=2,
        )


def plot_lines(ax: plt.Axes, lines: gpd.GeoDataFrame) -> None:
    for row in lines.sort_values("max_loading_pct").itertuples(index=False):
        x, y = row.geometry.xy
        if not row.active_in_year:
            linestyle = (0, (1, 2))
            color = "#BBC0BD"
            alpha = 0.55
            width = 0.65
        elif row.candidate:
            linestyle = (0, (4, 2.4))
            color = row.plot_color
            alpha = 0.86 if row.investment_decision > EPS else 0.48
            width = row.plot_width
        else:
            linestyle = "-"
            color = row.plot_color
            alpha = 0.9
            width = row.plot_width
        if row.active_in_year and row.loading_class == "80-95%":
            width *= 1.18
        if row.active_in_year:
            width *= 1.12
        width *= LINE_WIDTH_SCALE
        ax.plot(
            x,
            y,
            color=color,
            linewidth=width,
            linestyle=linestyle,
            alpha=alpha,
            solid_capstyle="round",
            dash_capstyle="round",
            zorder=3,
        )


def plot_nodes(ax: plt.Axes, nodes: gpd.GeoDataFrame) -> None:
    ax.scatter(
        nodes.geometry.x,
        nodes.geometry.y,
        s=15 * MARKER_AREA_SCALE,
        marker="o",
        facecolor=COLORS["node"],
        edgecolor="white",
        linewidth=0.55 * BORDER_WIDTH_SCALE,
        alpha=0.95,
        zorder=5,
    )


def capacity_marker_size(capacity_mw: Any) -> np.ndarray:
    values = np.asarray(capacity_mw, dtype=float)
    return MARKER_AREA_SCALE * 1.20 * (
        24.0 + 0.38 * np.clip(values, 0.0, None)
    )


def plot_generators(ax: plt.Axes, generators: gpd.GeoDataFrame) -> None:
    for group_name, style in GENERATION_STYLE.items():
        subset = generators[generators["technology_group"] == group_name]
        if subset.empty:
            continue
        selected = subset[subset["selected_in_2030"]]
        unselected = subset[~subset["selected_in_2030"]]
        if not selected.empty:
            ax.scatter(
                selected.geometry.x,
                selected.geometry.y,
                s=capacity_marker_size(selected["installed_mw"]),
                marker=style["marker"],
                facecolor=style["color"],
                edgecolor="#FFFFFF" if group_name == "oil" else "#28312C",
                linewidth=0.9 * BORDER_WIDTH_SCALE,
                alpha=0.95,
                zorder=7,
            )
        if not unselected.empty:
            ax.scatter(
                unselected.geometry.x,
                unselected.geometry.y,
                s=capacity_marker_size(unselected["installed_mw"]),
                marker=style["marker"],
                facecolor="white",
                edgecolor=style["color"],
                linewidth=1.25 * BORDER_WIDTH_SCALE,
                alpha=0.95,
                zorder=7,
            )


def plot_ens(ax: plt.Axes, ens: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    nonzero = ens[ens["ens_gwh"] > EPS].copy()
    if nonzero.empty:
        return nonzero
    maximum = finite_float(nonzero["ens_gwh"].max(), 1.0)
    sizes = MARKER_AREA_SCALE * (
        48 + 500 * nonzero["ens_gwh"] / maximum
    )
    ax.scatter(
        nonzero.geometry.x,
        nonzero.geometry.y,
        s=sizes,
        marker="o",
        facecolor="none",
        edgecolor=COLORS["ens"],
        linewidth=1.6 * BORDER_WIDTH_SCALE,
        alpha=0.95,
        zorder=9,
    )
    return nonzero


def plot_curtailment(
    ax: plt.Axes,
    curtailment: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    nonzero = curtailment[curtailment["curtailment_gwh"] > EPS].copy()
    if nonzero.empty:
        return nonzero
    maximum = finite_float(nonzero["curtailment_gwh"].max(), 1.0)
    sizes = MARKER_AREA_SCALE * (
        70 + 480 * nonzero["curtailment_gwh"] / maximum
    )
    ax.scatter(
        nonzero.geometry.x,
        nonzero.geometry.y,
        s=sizes,
        marker="*",
        facecolor=COLORS["curtailment"],
        edgecolor="#075B72",
        linewidth=0.8 * BORDER_WIDTH_SCALE,
        alpha=0.88,
        zorder=10,
    )
    return nonzero


def annotate_important_elements(
    ax: plt.Axes,
    ens: gpd.GeoDataFrame,
    curtailment: gpd.GeoDataFrame,
    lines_to_label: gpd.GeoDataFrame,
    *,
    include_ens: bool = True,
    include_curtailment: bool = True,
    compact_lines: bool = False,
    nodes_to_label: gpd.GeoDataFrame | None = None,
    generators_to_label: gpd.GeoDataFrame | None = None,
) -> None:
    texts: list[Any] = []
    target_x: list[float] = []
    target_y: list[float] = []
    line_label_artists: list[Any] = []

    ax.figure.canvas.draw()
    renderer = ax.figure.canvas.get_renderer()
    axes_bbox = ax.get_window_extent(renderer)
    occupied_bboxes = [
        artist.get_window_extent(renderer).expanded(1.06, 1.18)
        for artist in ax.texts
        if artist.get_visible()
    ]

    def overlap_area(candidate: Any, occupied: Any) -> float:
        width = max(
            0.0,
            min(candidate.x1, occupied.x1) - max(candidate.x0, occupied.x0),
        )
        height = max(
            0.0,
            min(candidate.y1, occupied.y1) - max(candidate.y0, occupied.y0),
        )
        return width * height

    for row in lines_to_label.itertuples(index=False):
        label = f"{row.max_loading_pct:.1f}%"
        color = "#4C2527" if row.max_loading_pct >= 80 else "#60472F"
        text_kwargs = {
            "fontsize": publication_font_size(
                10.0 if compact_lines else 10.8
            ),
            "color": color,
            "ha": "center",
            "fontweight": "bold",
            "path_effects": [
                patheffects.withStroke(
                    linewidth=3.0 * HALO_WIDTH_SCALE,
                    foreground="white",
                    alpha=0.96,
                )
            ],
            "zorder": 15,
        }
        candidates: list[tuple[tuple[Any, ...], Point, Any, str]] = []
        for fraction in (0.50, 0.35, 0.65, 0.20, 0.80, 0.10, 0.90):
            point = row.geometry.interpolate(fraction, normalized=True)
            for vertical_alignment in ("center", "bottom", "top"):
                probe = ax.text(
                    point.x,
                    point.y,
                    label,
                    alpha=0.0,
                    va=vertical_alignment,
                    **text_kwargs,
                )
                candidate_bbox = probe.get_window_extent(renderer).expanded(
                    1.06,
                    1.18,
                )
                probe.remove()
                outside_width = max(
                    0.0,
                    axes_bbox.x0 - candidate_bbox.x0,
                ) + max(
                    0.0,
                    candidate_bbox.x1 - axes_bbox.x1,
                )
                outside_height = max(
                    0.0,
                    axes_bbox.y0 - candidate_bbox.y0,
                ) + max(
                    0.0,
                    candidate_bbox.y1 - axes_bbox.y1,
                )
                outside_area = (
                    outside_width * candidate_bbox.height
                    + outside_height * candidate_bbox.width
                )
                collision_area = sum(
                    overlap_area(candidate_bbox, occupied)
                    for occupied in occupied_bboxes
                )
                score = (
                    outside_area > EPS,
                    collision_area > EPS,
                    outside_area,
                    collision_area,
                    abs(fraction - 0.50),
                    vertical_alignment != "center",
                )
                candidates.append(
                    (
                        score,
                        point,
                        candidate_bbox,
                        vertical_alignment,
                    )
                )

        _, point, _, vertical_alignment = min(
            candidates,
            key=lambda candidate: candidate[0],
        )
        text = ax.text(
            point.x,
            point.y,
            label,
            va=vertical_alignment,
            **text_kwargs,
        )
        occupied_bboxes.append(
            text.get_window_extent(renderer).expanded(1.06, 1.18)
        )
        line_label_artists.append(text)

    if include_ens:
        minimum_x, maximum_x = ax.get_xlim()
        horizontal_span = maximum_x - minimum_x
        for row in ens.sort_values("ens_gwh", ascending=False).itertuples(
            index=False
        ):
            relative_x = (row.geometry.x - minimum_x) / horizontal_span
            direction = -1.0 if relative_x > 0.82 else 1.0
            text = ax.text(
                row.geometry.x + direction * 0.010 * horizontal_span,
                row.geometry.y,
                f"{row.ens_mwh:.0f} MWh",
                fontsize=publication_font_size(11.0),
                color=COLORS["ens"],
                ha="right" if direction < 0 else "left",
                va="center",
                fontweight="bold",
                path_effects=[
                    patheffects.withStroke(
                        linewidth=2.4 * HALO_WIDTH_SCALE,
                        foreground="white",
                        alpha=0.96,
                    )
                ],
                zorder=13,
            )
            texts.append(text)
            target_x.append(row.geometry.x)
            target_y.append(row.geometry.y)

    if include_curtailment:
        for row in curtailment.nlargest(5, "curtailment_gwh").itertuples(index=False):
            text = ax.text(
                row.geometry.x,
                row.geometry.y,
                f"Curtailment = {row.curtailment_gwh:.2f} GWh",
                fontsize=publication_font_size(11.0),
                color="#006A80",
                ha="center",
                va="center",
                fontweight="bold",
                bbox={
                    "boxstyle": f"round,pad={TEXT_BOX_PAD}",
                    "facecolor": "white",
                    "edgecolor": "#B9DEE6",
                    "linewidth": 0.35 * BORDER_WIDTH_SCALE,
                    "alpha": 0.91,
                },
                zorder=13,
            )
            texts.append(text)
            target_x.append(row.geometry.x)
            target_y.append(row.geometry.y)

    if nodes_to_label is not None:
        for row in nodes_to_label.itertuples(index=False):
            text = ax.text(
                row.geometry.x,
                row.geometry.y,
                short_node(row.Node).replace("_", " "),
                fontsize=publication_font_size(10.2),
                color=COLORS["ink"],
                ha="center",
                va="center",
                fontweight="bold",
                path_effects=[
                    patheffects.withStroke(
                        linewidth=3.0 * HALO_WIDTH_SCALE,
                        foreground="white",
                        alpha=0.96,
                    )
                ],
                zorder=14,
            )
            texts.append(text)
            target_x.append(row.geometry.x)
            target_y.append(row.geometry.y)

    if generators_to_label is not None:
        for row in generators_to_label.itertuples(index=False):
            style = GENERATION_STYLE.get(
                row.technology_group,
                GENERATION_STYLE["other"],
            )
            text = ax.text(
                row.geometry.x,
                row.geometry.y,
                str(row.Generator).replace("_", " "),
                fontsize=publication_font_size(9.8),
                color=style["color"],
                ha="center",
                va="center",
                fontweight="bold",
                bbox={
                    "boxstyle": f"round,pad={TEXT_BOX_PAD}",
                    "facecolor": "white",
                    "edgecolor": style["color"],
                    "linewidth": 0.4 * BORDER_WIDTH_SCALE,
                    "alpha": 0.88,
                },
                zorder=14,
            )
            texts.append(text)
            target_x.append(row.geometry.x)
            target_y.append(row.geometry.y)

    if texts:
        adjust_text(
            texts,
            ax=ax,
            x=target_x,
            y=target_y,
            target_x=target_x,
            target_y=target_y,
            objects=line_label_artists or None,
            avoid_self=True,
            prevent_crossings=True,
            expand=(1.22, 1.34),
            force_text=(0.62, 0.86),
            force_static=(0.30, 0.44),
            force_pull=(0.025, 0.04),
            force_explode=(0.45, 0.72),
            max_move=(52, 64),
            ensure_inside_axes=True,
            expand_axes=False,
            min_arrow_len=3.0,
            iter_lim=1000,
            arrowprops={
                "arrowstyle": "-",
                "color": "#7C827F",
                "lw": 0.65 * LINE_WIDTH_SCALE,
                "alpha": 0.8,
            },
        )


def dakar_congestion_extent(
    nodes: gpd.GeoDataFrame,
    lines: gpd.GeoDataFrame,
) -> tuple[float, float, float, float]:
    node_names = nodes["Node"].map(normalized)
    anchors = nodes[
        nodes["zone"].eq("Dakar") | node_names.str.contains("tobene")
    ]
    if anchors.empty:
        raise ValueError("No Dakar substations were found for the zoom extent.")

    anchor_area = unary_union(anchors.geometry.tolist()).buffer(15_000.0)
    nearby_loaded = lines[
        lines["active_in_year"]
        & (lines["max_loading_pct"] >= 50.0)
        & lines.geometry.intersects(anchor_area)
    ]
    extent_geometry = unary_union(
        anchors.geometry.tolist() + nearby_loaded.geometry.tolist()
    )
    minimum_x, minimum_y, maximum_x, maximum_y = extent_geometry.bounds
    padding_x = max(6_000.0, 0.08 * (maximum_x - minimum_x))
    padding_y = max(5_000.0, 0.10 * (maximum_y - minimum_y))
    return (
        minimum_x - padding_x,
        minimum_y - padding_y,
        maximum_x + padding_x,
        maximum_y + padding_y,
    )


def dakar_thies_extent(
    nodes: gpd.GeoDataFrame,
) -> tuple[float, float, float, float]:
    subset = nodes[nodes["zone"].isin(["Dakar", "Thies"])]
    minimum_x, minimum_y, maximum_x, maximum_y = subset.total_bounds
    padding_x = 0.055 * (maximum_x - minimum_x)
    padding_y = 0.085 * (maximum_y - minimum_y)
    return (
        minimum_x - padding_x,
        minimum_y - padding_y,
        maximum_x + padding_x,
        maximum_y + padding_y,
    )


def lines_inside_extent(
    lines: gpd.GeoDataFrame,
    extent: tuple[float, float, float, float],
) -> pd.Series:
    minimum_x, minimum_y, maximum_x, maximum_y = extent
    centroids = lines.geometry.centroid
    return (
        centroids.x.between(minimum_x, maximum_x)
        & centroids.y.between(minimum_y, maximum_y)
    )


def add_cartographic_elements(ax: plt.Axes) -> None:
    ax.annotate(
        "N",
        xy=(0.055, 0.90),
        xytext=(0.055, 0.825),
        xycoords="axes fraction",
        textcoords="axes fraction",
        ha="center",
        va="bottom",
        fontsize=publication_font_size(10.0),
        fontweight="bold",
        arrowprops={
            "arrowstyle": "-|>",
            "color": COLORS["ink"],
            "lw": 1.0 * LINE_WIDTH_SCALE,
            "mutation_scale": publication_font_size(9.0),
        },
        zorder=20,
    )

    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()
    target_length = 0.30 * (x_max - x_min)
    magnitude = 10 ** math.floor(math.log10(target_length))
    length = max(
        value * magnitude
        for value in (1.0, 2.0, 5.0, 10.0)
        if value * magnitude <= target_length
    )
    x_start = x_min + 0.055 * (x_max - x_min)
    y_start = y_min + 0.045 * (y_max - y_min)
    ax.plot(
        [x_start, x_start + length],
        [y_start, y_start],
        color=COLORS["ink"],
        linewidth=1.2 * LINE_WIDTH_SCALE,
        zorder=20,
    )
    for x_value in (x_start, x_start + length):
        ax.plot(
            [x_value, x_value],
            [
                y_start - 0.007 * (y_max - y_min),
                y_start + 0.007 * (y_max - y_min),
            ],
            color=COLORS["ink"],
            linewidth=0.9 * LINE_WIDTH_SCALE,
            zorder=20,
        )
    ax.text(
        x_start + length / 2,
        y_start + 0.012 * (y_max - y_min),
        f"{length / 1000:g} km",
        ha="center",
        va="bottom",
        fontsize=publication_font_size(8.2),
        color=COLORS["ink"],
        zorder=20,
    )


def draw_legend_panel(
    fig: plt.Figure,
    generators: gpd.GeoDataFrame,
) -> None:
    legend_ax = fig.add_axes([0.71, 0.08, 0.28, 0.84])
    legend_ax.set_xlim(0, 1)
    legend_ax.set_ylim(0, 1)
    legend_ax.set_xticks([])
    legend_ax.set_yticks([])
    legend_ax.set_facecolor("white")
    for spine in legend_ax.spines.values():
        spine.set_color("#C9CECB")
        spine.set_linewidth(0.9 * BORDER_WIDTH_SCALE)

    legend_ax.text(
        0.06,
        0.95,
        "LEGEND",
        fontsize=publication_font_size(15.5),
        fontweight="bold",
        color=COLORS["ink"],
    )
    legend_ax.text(
        0.06,
        0.86,
        "Generation technologies",
        fontsize=publication_font_size(13.5),
        fontweight="bold",
        color=COLORS["muted"],
    )
    present = [
        group
        for group in ("solar", "wind", "hydro", "gas", "oil", "battery", "other")
        if (generators["technology_group"] == group).any()
    ]
    for position, group in enumerate(present):
        column = position % 2
        row = position // 2
        x = 0.09 + 0.48 * column
        y = 0.765 - 0.115 * row
        style = GENERATION_STYLE[group]
        legend_ax.scatter(
            [x],
            [y],
            s=90 * MARKER_AREA_SCALE,
            marker=style["marker"],
            facecolor=style["color"],
            edgecolor="#28312C",
            linewidth=0.8 * BORDER_WIDTH_SCALE,
            clip_on=False,
        )
        legend_ax.text(
            x + 0.075,
            y,
            style["label"],
            va="center",
            fontsize=publication_font_size(12.2),
            fontweight="bold",
            color=COLORS["ink"],
        )

    legend_ax.text(
        0.06,
        0.47,
        "Network indicators",
        fontsize=publication_font_size(13.5),
        fontweight="bold",
        color=COLORS["muted"],
    )
    loading_items = [
        ("0-50%", COLORS["loading_low"]),
        ("50-80%", COLORS["loading_medium"]),
        ("80-95%", COLORS["loading_high"]),
        (">=95%", COLORS["loading_critical"]),
    ]
    for position, (label, color) in enumerate(loading_items):
        column = position % 2
        row = position // 2
        x = 0.07 + 0.48 * column
        y = 0.365 - 0.115 * row
        width = 3.7 if label == "80-95%" else 3.2
        legend_ax.plot(
            [x, x + 0.13],
            [y, y],
            color=color,
            linewidth=width * LINE_WIDTH_SCALE,
        )
        legend_ax.text(
            x + 0.17,
            y,
            label,
            va="center",
            fontsize=publication_font_size(11.5),
            fontweight="bold",
            color=COLORS["ink"],
        )

    legend_ax.plot(
        [0.07, 0.20],
        [0.165, 0.165],
        color=COLORS["candidate"],
        linewidth=2.0 * LINE_WIDTH_SCALE,
        linestyle=(0, (4, 2)),
    )
    legend_ax.text(
        0.24,
        0.165,
        "Candidate line",
        va="center",
        fontsize=publication_font_size(11.3),
        fontweight="bold",
        color=COLORS["ink"],
    )
    legend_ax.scatter(
        [0.09],
        [0.10],
        s=38 * MARKER_AREA_SCALE,
        facecolor=COLORS["node"],
        edgecolor="white",
        linewidth=0.55 * BORDER_WIDTH_SCALE,
    )
    legend_ax.text(
        0.18,
        0.10,
        "Substations",
        va="center",
        fontsize=publication_font_size(11.3),
        fontweight="bold",
        color=COLORS["ink"],
    )
    legend_ax.scatter(
        [0.09],
        [0.035],
        s=165 * MARKER_AREA_SCALE,
        facecolor="none",
        edgecolor=COLORS["ens"],
        linewidth=1.8 * BORDER_WIDTH_SCALE,
    )
    legend_ax.text(
        0.18,
        0.035,
        "ENS",
        va="center",
        fontsize=publication_font_size(12.0),
        fontweight="bold",
        color=COLORS["ink"],
    )


def combined_map_extent(
    frames: Iterable[gpd.GeoDataFrame],
) -> tuple[float, float, float, float]:
    bounds = np.vstack([frame.total_bounds for frame in frames if not frame.empty])
    minimum_x = float(bounds[:, 0].min())
    minimum_y = float(bounds[:, 1].min())
    maximum_x = float(bounds[:, 2].max())
    maximum_y = float(bounds[:, 3].max())
    padding_x = 0.045 * (maximum_x - minimum_x)
    padding_y = 0.055 * (maximum_y - minimum_y)
    return (
        minimum_x - padding_x,
        minimum_y - padding_y,
        maximum_x + padding_x,
        maximum_y + padding_y,
    )


def points_inside_extent(
    points: gpd.GeoDataFrame,
    extent: tuple[float, float, float, float],
) -> pd.Series:
    minimum_x, minimum_y, maximum_x, maximum_y = extent
    return (
        points.geometry.x.between(minimum_x, maximum_x)
        & points.geometry.y.between(minimum_y, maximum_y)
    )


def render_spatial_map(
    regions: gpd.GeoDataFrame,
    lines: gpd.GeoDataFrame,
    nodes: gpd.GeoDataFrame,
    generators: gpd.GeoDataFrame,
    ens: gpd.GeoDataFrame,
    curtailment: gpd.GeoDataFrame,
    png_path: Path,
    pdf_path: Path,
    svg_path: Path,
    *,
    extent: tuple[float, float, float, float] | None = None,
    line_label_count: int = 1,
    compact_line_labels: bool = False,
    metadata_title: str,
    show_legend: bool = True,
    label_assets: bool = False,
) -> tuple[int, int]:
    fig = plt.figure(figsize=FIGURE_SIZE, facecolor="white")
    map_width = 0.68 if show_legend else 0.96
    ax = fig.add_axes([0.02, 0.035, map_width, 0.93])
    ax.set_facecolor("white")

    plot_regions(ax, regions)
    plot_lines(ax, lines)
    plot_nodes(ax, nodes)
    plot_generators(ax, generators)
    ens_nonzero = plot_ens(ax, ens)
    curtailment_nonzero = plot_curtailment(ax, curtailment)

    if extent is None:
        extent = combined_map_extent((regions, nodes, generators, lines))
    ax.set_xlim(extent[0], extent[2])
    ax.set_ylim(extent[1], extent[3])
    ax.set_aspect("equal", adjustable="box")
    ax.set_axis_off()

    visible_ens = ens_nonzero.loc[points_inside_extent(ens_nonzero, extent)]
    visible_curtailment = curtailment_nonzero.loc[
        points_inside_extent(curtailment_nonzero, extent)
    ]
    eligible_lines = lines[
        lines["active_in_year"] & (lines["max_loading_pct"] > 0)
    ]
    eligible_lines = eligible_lines.loc[
        lines_inside_extent(eligible_lines, extent)
    ].nlargest(line_label_count, "max_loading_pct")

    visible_nodes = nodes.loc[points_inside_extent(nodes, extent)].copy()
    labelled_line_nodes = set(eligible_lines["InitialNode"]) | set(
        eligible_lines["FinalNode"]
    )
    active_lines = lines[lines["active_in_year"]]
    endpoint_degree = pd.concat(
        [active_lines["InitialNode"], active_lines["FinalNode"]]
    ).value_counts()
    visible_nodes["plot_degree"] = (
        visible_nodes["Node"].map(endpoint_degree).fillna(0)
    )
    nodes_to_label = (
        visible_nodes[~visible_nodes["Node"].isin(labelled_line_nodes)]
        .sort_values(["plot_degree", "Node"], ascending=[False, True])
        .head(3)
    )

    visible_generators = generators.loc[
        points_inside_extent(generators, extent)
        & generators["selected_in_2030"]
        & (generators["installed_mw"] > EPS)
    ]
    generators_to_label = (
        visible_generators.sort_values("installed_mw", ascending=False)
        .drop_duplicates("Node")
        .head(4)
    )

    annotate_important_elements(
        ax,
        visible_ens,
        visible_curtailment,
        eligible_lines,
        compact_lines=compact_line_labels,
        nodes_to_label=nodes_to_label if label_assets else None,
        generators_to_label=generators_to_label if label_assets else None,
    )
    add_cartographic_elements(ax)
    if show_legend:
        draw_legend_panel(fig, generators)

    fig.savefig(
        png_path,
        dpi=OUTPUT_DPI,
        bbox_inches="tight",
        pad_inches=0.12,
        metadata={"Title": metadata_title},
    )
    fig.savefig(
        pdf_path,
        dpi=OUTPUT_DPI,
        bbox_inches="tight",
        pad_inches=0.12,
        metadata={
            "Title": metadata_title,
            "Subject": "OpenTEPES network, generation, and ENS",
            "Creator": "Python, GeoPandas, and Matplotlib",
        },
    )
    fig.savefig(
        svg_path,
        format="svg",
        dpi=OUTPUT_DPI,
        bbox_inches="tight",
        pad_inches=0.12,
        metadata={
            "Title": metadata_title,
            "Description": "OpenTEPES network, generation, and ENS",
            "Creator": "Python, GeoPandas, and Matplotlib",
        },
    )
    plt.close(fig)
    return len(visible_ens), len(visible_curtailment)


def save_processed_geodata(
    files: CaseFiles,
    regions: gpd.GeoDataFrame,
    nodes: gpd.GeoDataFrame,
    generators: gpd.GeoDataFrame,
    lines: gpd.GeoDataFrame,
    ens: gpd.GeoDataFrame,
    curtailment: gpd.GeoDataFrame,
    kpis: dict[str, Any],
) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    layers = {
        "regions": regions,
        "nodes": nodes,
        "generators": generators,
        "transmission_lines": lines,
        "ens_nodes": ens,
        "curtailment_nodes": curtailment,
    }
    for name, layer in layers.items():
        output = PROCESSED_DIR / f"{name}.geojson"
        layer.to_crs("EPSG:4326").to_file(output, driver="GeoJSON")

    top_lines = lines.nlargest(5, "max_loading_pct")[
        [
            "corridor_name",
            "max_loading_pct",
            "p95_abs_flow_mw",
            "max_abs_flow_mw",
            "peak_load_level",
        ]
    ]
    top_lines.to_csv(PROCESSED_DIR / "top_congested_corridors.csv", index=False)
    ens.nlargest(5, "ens_gwh")[
        ["Node", "zone", "ens_gwh", "ens_mwh"]
    ].to_csv(PROCESSED_DIR / "top_ens_nodes.csv", index=False)
    manifest = {
        "sources": {
            key: str(value.relative_to(ROOT)) if value else None
            for key, value in asdict(files).items()
        },
        "kpis": {
            key: finite_float(value) if isinstance(value, (float, np.floating)) else value
            for key, value in kpis.items()
        },
        "crs": {
            "source": "EPSG:4326",
            "plot": TARGET_CRS,
        },
        "loading_definition": "max(abs(flow)) / (TTC * SecurityFactor)",
        "line_width_definition": "95th-percentile absolute flow",
        "documentation": "https://opentepes.readthedocs.io/en/latest/InputData.html",
    }
    (PROCESSED_DIR / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    files = discover_files()
    geodata = load_geodata(files)
    network, flows, network_investments = load_network(files, geodata["nodes"])
    results = load_results(files, geodata)
    network = compute_loading(
        network,
        flows,
        network_investments,
        results["year"],
    )
    results["kpis"]["peak_loading_pct"] = finite_float(
        network.loc[network["active_in_year"], "max_loading_pct"].max()
    )

    regions_plot = geodata["regions"].to_crs(TARGET_CRS)
    nodes_plot = geodata["nodes"].to_crs(TARGET_CRS)
    generators_plot = results["generators"].to_crs(TARGET_CRS)
    ens_plot = results["ens"].to_crs(TARGET_CRS)
    curtailment_plot = results["curtailment"].to_crs(TARGET_CRS)
    lines_plot = offset_parallel_lines(network.to_crs(TARGET_CRS))

    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": publication_font_size(10.0),
            "axes.titlesize": publication_font_size(14.0),
            "axes.labelsize": publication_font_size(10.0),
            "legend.fontsize": publication_font_size(11.0),
            "legend.title_fontsize": publication_font_size(13.0),
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "savefig.dpi": OUTPUT_DPI,
            "savefig.facecolor": "white",
        }
    )
    np.random.seed(2030)
    national_ens_count, national_curtailment_count = render_spatial_map(
        regions_plot,
        lines_plot,
        nodes_plot,
        generators_plot,
        ens_plot,
        curtailment_plot,
        NATIONAL_PNG_PATH,
        NATIONAL_PDF_PATH,
        NATIONAL_SVG_PATH,
        line_label_count=1,
        metadata_title="Senegal 2030 spatial diagnostic",
        show_legend=True,
        label_assets=False,
    )
    dakar_thies_ens_count, dakar_thies_curtailment_count = render_spatial_map(
        regions_plot,
        lines_plot,
        nodes_plot,
        generators_plot,
        ens_plot,
        curtailment_plot,
        DAKAR_THIES_PNG_PATH,
        DAKAR_THIES_PDF_PATH,
        DAKAR_THIES_SVG_PATH,
        extent=dakar_congestion_extent(nodes_plot, lines_plot),
        line_label_count=4,
        metadata_title="Senegal 2030 spatial diagnostic - Dakar congestion zoom",
        show_legend=True,
        label_assets=False,
    )

    save_processed_geodata(
        files,
        geodata["regions"],
        geodata["nodes"],
        results["generators"],
        network,
        results["ens"],
        results["curtailment"],
        results["kpis"],
    )

    print("Discovered files:")
    for role, path in asdict(files).items():
        print(f"  {role:24s} {path.relative_to(ROOT) if path else 'not found'}")
    print("\nDiagnostics:")
    print(f"  active model circuits    {int(network['active_in_year'].sum())}")
    print(f"  generators plotted       {len(results['generators'])}")
    print(f"  ENS nodes, national      {national_ens_count}")
    print(f"  ENS nodes, Dakar-Thies   {dakar_thies_ens_count}")
    print(f"  curtailment, national    {national_curtailment_count}")
    print(f"  curtailment, Dakar-Thies {dakar_thies_curtailment_count}")
    print(f"  total ENS                {results['kpis']['ens_gwh']:.6f} GWh")
    print(
        f"  total curtailment        "
        f"{results['kpis']['curtailment_gwh']:.6f} GWh"
    )
    print(
        f"  renewable share          "
        f"{results['kpis']['renewable_share_pct']:.3f}%"
    )
    print(
        f"  peak loading             "
        f"{results['kpis']['peak_loading_pct']:.3f}%"
    )
    print(f"\nWrote {NATIONAL_PNG_PATH.relative_to(ROOT)}")
    print(f"Wrote {NATIONAL_PDF_PATH.relative_to(ROOT)}")
    print(f"Wrote {NATIONAL_SVG_PATH.relative_to(ROOT)}")
    print(f"Wrote {DAKAR_THIES_PNG_PATH.relative_to(ROOT)}")
    print(f"Wrote {DAKAR_THIES_PDF_PATH.relative_to(ROOT)}")
    print(f"Wrote {DAKAR_THIES_SVG_PATH.relative_to(ROOT)}")
    print(f"Wrote {PROCESSED_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
