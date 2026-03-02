import os

import panel as pn
import hvplot.pandas  # noqa: F401 (register hvplot on pandas/geopandas)
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
from sqlalchemy import create_engine

pn.extension("leaflet")

# ----------------------------
# Grid resolution
# ----------------------------
lat_step = 0.0009
lon_step = 0.0018

SQL = """
WITH parked AS (
    SELECT
        vin,
        reading_ts,
        FLOOR(latitude  / 0.0009)::bigint  AS lat_bin,
        FLOOR(longitude / 0.0018)::bigint  AS lon_bin
    FROM vehicle_telemetry
    WHERE latitude  IS NOT NULL
      AND longitude IS NOT NULL
      AND reading_ts IS NOT NULL
),
with_deltas AS (
    SELECT
        vin,
        lat_bin,
        lon_bin,
        reading_ts,
        LEAD(reading_ts) OVER (
            PARTITION BY vin
            ORDER BY reading_ts
        ) AS next_ts
    FROM parked
),
cell_time AS (
    SELECT
        vin,
        lat_bin,
        lon_bin,
        SUM(EXTRACT(EPOCH FROM (next_ts - reading_ts))) AS seconds_parked
    FROM with_deltas
    WHERE next_ts IS NOT NULL
    GROUP BY vin, lat_bin, lon_bin
),
origin AS (
    SELECT
        lat_bin AS origin_lat_bin,
        lon_bin AS origin_lon_bin
    FROM (
        SELECT
            lat_bin,
            lon_bin,
            SUM(seconds_parked) AS total_seconds_parked
        FROM cell_time
        GROUP BY lat_bin, lon_bin
        ORDER BY total_seconds_parked DESC
        LIMIT 1
    ) o
)
SELECT
    ct.vin,
    (ct.lat_bin * 0.0009)::numeric(10,7)  AS lat_100m,
    (ct.lon_bin * 0.0018)::numeric(10,7)  AS lon_100m,
    (o.origin_lat_bin * 0.0009 + 0.0009 / 2)::numeric(10,7) AS origin_lat_100m,
    (o.origin_lon_bin * 0.0018 + 0.0018 / 2)::numeric(10,7) AS origin_lon_100m,
    ct.seconds_parked,
    ROUND(ct.seconds_parked / 3600.0, 4)  AS hours_parked,
    ROUND(ct.seconds_parked / 86400.0, 3)::numeric(10,3) AS days_parked,
    ((ct.lon_bin - o.origin_lon_bin) * 100)::bigint AS delta_x_m,
    ((ct.lat_bin - o.origin_lat_bin) * 100)::bigint AS delta_y_m,
    ROUND(
        SQRT(
            POWER(((ct.lon_bin - o.origin_lon_bin) * 100)::numeric, 2) +
            POWER(((ct.lat_bin - o.origin_lat_bin) * 100)::numeric, 2)
        )
    )::bigint AS distance_m
FROM cell_time ct
CROSS JOIN origin o
ORDER BY ct.seconds_parked DESC;
"""

# ----------------------------
# Configuration via environment
# ----------------------------
DBURL = "postgresql+psycopg2://erling:Gnilre_22@www.accretiosolutions.com:5432/linuxdatabase"

# Optional noise filter threshold (hours)
MIN_HOURS = 0.5

# ----------------------------
# Data load + transform helpers
# ----------------------------
def load_data():
    engine = create_engine(DBURL)
    df = pd.read_sql(SQL, engine)

    # Ensure correct dtypes
    df["lat_100m"] = df["lat_100m"].astype(float)
    df["lon_100m"] = df["lon_100m"].astype(float)
    df["hours_parked"] = df["hours_parked"].astype(float)

    # Optional noise filter
    df = df[df["hours_parked"] >= MIN_HOURS].copy()
    return df

def cell_polygon(row):
    x = row["lon_100m"]
    y = row["lat_100m"]
    return Polygon([
        (x, y),
        (x + lon_step, y),
        (x + lon_step, y + lat_step),
        (x, y + lat_step),
        (x, y),
    ])

def build_plot(df: pd.DataFrame):
    gdf = gpd.GeoDataFrame(
        df,
        geometry=df.apply(cell_polygon, axis=1),
        crs="EPSG:4326",
    )

    squares = gdf.hvplot.polygons(
        geo=True,
        tiles="OSM",
        c="hours_parked",
        cmap="viridis",
        alpha=0.55,
        line_color="black",
        line_width=0.6,
        hover_cols=["hours_parked", "days_parked"],
        frame_height=700,
        frame_width=1000,
        title="Parking grid (100×100 m cells, colored by hours parked)",
    )

    origin_lat = float(df["origin_lat_100m"].iloc[0])
    origin_lon = float(df["origin_lon_100m"].iloc[0])

    origin_df = pd.DataFrame({"lon": [origin_lon], "lat": [origin_lat]})
    origin = origin_df.hvplot.points(
        x="lon",
        y="lat",
        geo=True,
        tiles="OSM",
        color="red",
        marker="x",
        size=350,
    )

    return squares * origin

# ----------------------------
# Panel app with refresh button
# ----------------------------
status = pn.pane.Alert("", alert_type="info", visible=False)
plot_pane = pn.pane.HoloViews(sizing_mode="stretch_width")
refresh = pn.widgets.Button(name="Refresh data", button_type="primary")
min_hours = pn.widgets.FloatInput(name="Min parked hours", value=MIN_HOURS, step=0.25)

def _reload(event=None):
    try:
        status.visible = False
        df = load_data()
        plot_pane.object = build_plot(df)
        status.object = f"Loaded {len(df):,} rows (filtered >= {min_hours.value} hours)."
        status.alert_type = "success"
        status.visible = True
    except Exception as e:
        status.object = f"Error loading/plotting: {e}"
        status.alert_type = "danger"
        status.visible = True

def _min_hours_changed(event):
    os.environ["VEHICLEMAP_MIN_HOURS"] = str(event.new)
    # Use widget value for filtering
    global MIN_HOURS
    MIN_HOURS = float(event.new)
    _reload()

refresh.on_click(_reload)
min_hours.param.watch(_min_hours_changed, "value")

# Initial load
_reload()

app = pn.Column(
    "## Parking Lot Analysis – 100 m Grid",
    pn.pane.Markdown(
        """
**Each square represents a 100×100 m grid cell**  
Color = total parked hours  
Red ✕ = origin (center of most-used cell)
"""
    ),
    pn.Row(refresh, min_hours),
    status,
    plot_pane,
)

app.servable()