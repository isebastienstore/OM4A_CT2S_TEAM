from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from plot_senegal_spatial_diagnostic import (
    COLORS,
    GENERATION_STYLE,
    TARGET_CRS,
    add_cartographic_elements,
    load_regions,
    locate_generators,
    plot_generators,
    plot_regions,
    short_zone,
    technology_group,
)


CASE_ROOT = Path(
    r"C:\Users\DELL\OpenMod4A\openTEPESS\workspace\Results\2022\SN2022"
)
VIZ_DIR = CASE_ROOT / "viz"
OUTPUT_DIR = CASE_ROOT / "figures"
PNG_PATH = OUTPUT_DIR / "senegal_network_overview_2022.png"
PDF_PATH = OUTPUT_DIR / "senegal_network_overview_2022.pdf"
YEAR = 2022

TRANSMISSION_COLOR = "#424C47"
DISTRIBUTION_COLOR = "#8D9B94"


def load_nodes() -> gpd.GeoDataFrame:
    locations = pd.read_csv(CASE_ROOT / "oT_Data_NodeLocation_SN2022.csv")
    zones = pd.read_csv(CASE_ROOT / "oT_Dict_NodeToZone_SN2022.csv")
    frame = locations.merge(zones, on="Node", how="left")
    frame["zone"] = frame["Zone"].map(short_zone)
    return gpd.GeoDataFrame(
        frame,
        geometry=gpd.points_from_xy(frame["Longitude"], frame["Latitude"]),
        crs="EPSG:4326",
    )


def load_generators(nodes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    generation = pd.read_csv(CASE_ROOT / "oT_Data_Generation_SN2022.csv")
    initial = pd.to_numeric(generation["InitialPeriod"], errors="coerce").fillna(-np.inf)
    final = pd.to_numeric(generation["FinalPeriod"], errors="coerce").fillna(np.inf)
    generation = generation[(initial <= YEAR) & (final >= YEAR)].copy()

    inventory = pd.read_csv(VIZ_DIR / "power_plants.csv", sep=";")
    inventory.columns = inventory.columns.str.strip()
    inventory["Name"] = inventory["Name"].astype(str).str.strip()
    inventory["X"] = pd.to_numeric(inventory["X"], errors="coerce")
    inventory["Y"] = pd.to_numeric(inventory["Y"], errors="coerce")
    inventory = inventory.dropna(subset=["X", "Y"])

    located = locate_generators(generation, nodes, inventory)
    located["technology_group"] = located.apply(
        lambda row: technology_group(row["Technology"], row.get("StorageType", "")),
        axis=1,
    )
    located["installed_mw"] = pd.to_numeric(
        located["MaximumPower"], errors="coerce"
    ).fillna(0.0)
    located["selected_in_2030"] = True
    return gpd.GeoDataFrame(
        located,
        geometry=gpd.points_from_xy(located["longitude"], located["latitude"]),
        crs="EPSG:4326",
    )


def load_network_layers() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    distribution_path = next(VIZ_DIR.glob("*HTA*.gpkg"))
    transmission_path = next(VIZ_DIR.glob("*HTB*.gpkg"))

    distribution = gpd.read_file(distribution_path)
    transmission = gpd.read_file(transmission_path)

    if "Statut" in transmission.columns:
        service = transmission["Statut"].fillna("").str.startswith("Service")
        transmission = transmission.loc[service].copy()
    elif "status" in transmission.columns:
        projected = transmission["status"].fillna("").str.contains(
            "projet", case=False
        )
        transmission = transmission.loc[~projected].copy()

    distribution = distribution[
        distribution.geometry.notna() & ~distribution.geometry.is_empty
    ].copy()
    transmission = transmission[
        transmission.geometry.notna() & ~transmission.geometry.is_empty
    ].copy()
    return distribution, transmission


def draw_legend(
    fig: plt.Figure,
    generators: gpd.GeoDataFrame,
) -> None:
    legend_ax = fig.add_axes([0.74, 0.245, 0.245, 0.51])
    legend_ax.set_xlim(0, 1)
    legend_ax.set_ylim(0, 1)
    legend_ax.set_xticks([])
    legend_ax.set_yticks([])
    legend_ax.set_facecolor("white")
    for spine in legend_ax.spines.values():
        spine.set_color("#C9CECB")
        spine.set_linewidth(0.9)

    legend_ax.text(
        0.06,
        0.94,
        "LEGEND",
        fontsize=14.0,
        fontweight="bold",
        color=COLORS["ink"],
    )
    legend_ax.text(
        0.06,
        0.85,
        "Generation technologies",
        fontsize=12.2,
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
        x = 0.10 + 0.47 * column
        y = 0.75 - 0.105 * row
        style = GENERATION_STYLE[group]
        legend_ax.scatter(
            [x],
            [y],
            s=88,
            marker=style["marker"],
            facecolor=style["color"],
            edgecolor="#28312C",
            linewidth=0.75,
            clip_on=False,
        )
        legend_ax.text(
            x + 0.075,
            y,
            style["label"],
            va="center",
            fontsize=11.0,
            fontweight="bold",
            color=COLORS["ink"],
        )

    legend_ax.text(
        0.06,
        0.43,
        "Network infrastructure",
        fontsize=12.2,
        fontweight="bold",
        color=COLORS["muted"],
    )
    legend_ax.plot(
        [0.08, 0.24],
        [0.32, 0.32],
        color=TRANSMISSION_COLOR,
        linewidth=3.2,
        solid_capstyle="round",
    )
    legend_ax.text(
        0.29,
        0.32,
        "Transmission (HTB)",
        va="center",
        fontsize=11.0,
        fontweight="bold",
        color=COLORS["ink"],
    )
    legend_ax.plot(
        [0.08, 0.24],
        [0.21, 0.21],
        color=DISTRIBUTION_COLOR,
        linewidth=2.4,
        solid_capstyle="round",
    )
    legend_ax.text(
        0.29,
        0.21,
        "Distribution (HTA)",
        va="center",
        fontsize=11.0,
        fontweight="bold",
        color=COLORS["ink"],
    )
    legend_ax.scatter(
        [0.16],
        [0.10],
        s=38,
        marker="o",
        facecolor=COLORS["node"],
        edgecolor="white",
        linewidth=0.5,
    )
    legend_ax.text(
        0.29,
        0.10,
        "Substations",
        va="center",
        fontsize=11.0,
        fontweight="bold",
        color=COLORS["ink"],
    )


def plot_network_overview(
    regions: gpd.GeoDataFrame,
    distribution: gpd.GeoDataFrame,
    transmission: gpd.GeoDataFrame,
    nodes: gpd.GeoDataFrame,
    generators: gpd.GeoDataFrame,
) -> None:
    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 9.5,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.facecolor": "white",
        }
    )

    regions_plot = regions.to_crs(TARGET_CRS)
    distribution_plot = distribution.to_crs(TARGET_CRS)
    transmission_plot = transmission.to_crs(TARGET_CRS)
    nodes_plot = nodes.to_crs(TARGET_CRS)
    generators_plot = generators.to_crs(TARGET_CRS)

    fig = plt.figure(figsize=(12.2, 8.0), facecolor="white")
    ax = fig.add_axes([0.02, 0.035, 0.70, 0.93])
    ax.set_facecolor("white")

    plot_regions(ax, regions_plot)
    distribution_plot.plot(
        ax=ax,
        color=DISTRIBUTION_COLOR,
        linewidth=0.44,
        alpha=0.80,
        zorder=2,
    )
    transmission_plot.plot(
        ax=ax,
        color=TRANSMISSION_COLOR,
        linewidth=1.25,
        alpha=0.92,
        zorder=3,
    )
    regions_plot.boundary.plot(
        ax=ax,
        color=COLORS["region_edge"],
        linewidth=0.78,
        zorder=4,
    )
    ax.scatter(
        nodes_plot.geometry.x,
        nodes_plot.geometry.y,
        s=15,
        marker="o",
        facecolor=COLORS["node"],
        edgecolor="white",
        linewidth=0.55,
        alpha=0.95,
        zorder=5,
    )
    plot_generators(ax, generators_plot)

    minimum_x, minimum_y, maximum_x, maximum_y = regions_plot.total_bounds
    padding_x = 0.035 * (maximum_x - minimum_x)
    padding_y = 0.045 * (maximum_y - minimum_y)
    ax.set_xlim(minimum_x - padding_x, maximum_x + padding_x)
    ax.set_ylim(minimum_y - padding_y, maximum_y + padding_y)
    ax.set_aspect("equal", adjustable="box")
    ax.set_axis_off()

    add_cartographic_elements(ax)
    draw_legend(fig, generators_plot)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        PNG_PATH,
        dpi=300,
        bbox_inches="tight",
        pad_inches=0.08,
        metadata={"Title": "Senegal 2022 power network overview"},
    )
    fig.savefig(
        PDF_PATH,
        bbox_inches="tight",
        pad_inches=0.08,
        metadata={
            "Title": "Senegal 2022 power network overview",
            "Subject": "OpenTEPES input network, generation, HTB, and HTA",
            "Creator": "Python, GeoPandas, and Matplotlib",
        },
    )
    plt.close(fig)


def main() -> None:
    regions = load_regions(VIZ_DIR / "reg-senegal-regroupe.json")
    nodes = load_nodes()
    generators = load_generators(nodes)
    distribution, transmission = load_network_layers()
    plot_network_overview(
        regions,
        distribution,
        transmission,
        nodes,
        generators,
    )

    print(f"Regions:              {len(regions)}")
    print(f"OpenTEPES nodes:      {len(nodes)}")
    print(f"Active generators:    {len(generators)}")
    print(f"Transmission lines:   {len(transmission)}")
    print(f"Distribution feeders: {len(distribution)}")
    print(f"Wrote {PNG_PATH}")
    print(f"Wrote {PDF_PATH}")


if __name__ == "__main__":
    main()
