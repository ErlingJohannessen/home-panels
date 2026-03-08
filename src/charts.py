import os
import panel as pn
import hvplot.pandas  # noqa
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from bokeh.palettes import Category10
import holoviews as hv

# Panel + HoloViews setup
pn.extension(sizing_mode="stretch_width")
pn.config.throttled = True
hv.extension("bokeh")

# -------------------------------------------------------------------
# Disable any residual active Bokeh tools (belt & suspenders)
# -------------------------------------------------------------------
def disable_all_tools_hook(plot, element):
    tb = getattr(plot.state, "toolbar", None)
    if tb is None:
        return
    tb.active_drag = None
    tb.active_scroll = None
    tb.active_tap = None
    tb.active_inspect = None

# -------------------------------------------------------------------
# Number formatting: no decimals, space as thousand separator
# -------------------------------------------------------------------
def format_kwh(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")

# -------------------------------------------------------------------
# Database (SAFE pattern: pull URL from env var)
# Set e.g.:
#   export TIBBER_DB_URL="postgresql://USER:PASSWORD@HOST/DBNAME"
# -------------------------------------------------------------------
DB_URL = os.getenv("TIBBER_DB_URL", "postgresql://erling:Gnilre_22@www.accretiosolutions.com/linuxdatabase")
engine = create_engine(DB_URL, pool_pre_ping=True)

# -------------------------------------------------------------------
# Load data
# -------------------------------------------------------------------
def load_data():
    sql = text("""
        SELECT
            ts,
            home_id,
            home_name,
            accumulated_consumption AS e_daily,
            last_meter_consumption AS e_total
        FROM tibber_measurements
        WHERE ts >= NOW() - INTERVAL '14 days'
        ORDER BY ts
    """)
    df = pd.read_sql(sql, engine)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"])
    df["ts_naive"] = df["ts"].dt.tz_convert(None)
    return df

# -------------------------------------------------------------------
# Power calculation
# -------------------------------------------------------------------
def compute_power_kW(df_home):
    g = df_home.sort_values("ts_naive").copy()

    dt_h = g["ts_naive"].diff().dt.total_seconds() / 3600.0
    dE = g["e_daily"].diff()
    dE = dE.where(dE >= 0, g["e_daily"])  # reset handling

    P = dE / dt_h
    P = P.where(dt_h > 0)

    out = np.full(len(P), np.nan)
    prev = np.nan
    for i, v in enumerate(P.to_numpy(dtype=float, na_value=np.nan)):
        if np.isnan(v):
            out[i] = prev
        elif np.isnan(prev) or abs(v - prev) <= 10.0:
            out[i] = v
            prev = v
        else:
            out[i] = prev

    g["P_kW"] = out
    return g

# -------------------------------------------------------------------
# Quick range helper
# -------------------------------------------------------------------
def apply_quick_range(label, slider, end_dt):
    end_dt = pd.Timestamp(end_dt)
    if label == "6h":
        slider.value = (end_dt - pd.Timedelta(hours=6), end_dt)
    elif label == "24h":
        slider.value = (end_dt - pd.Timedelta(hours=24), end_dt)
    elif label == "7d":
        slider.value = (end_dt - pd.Timedelta(days=7), end_dt)
    elif label == "14d":
        slider.value = (end_dt - pd.Timedelta(days=14), end_dt)
    else:
        slider.value = (slider.start, slider.end)

# -------------------------------------------------------------------
# Build one home block
# -------------------------------------------------------------------
def build_home_block(df_home, color):
    home_name = (
        df_home["home_name"].dropna().iloc[0]
        if df_home["home_name"].notna().any()
        else str(df_home["home_id"].iloc[0])
    )

    start = df_home["ts_naive"].min()
    end = df_home["ts_naive"].max()
    latest_total = float(df_home.sort_values("ts_naive")["e_total"].iloc[-1])

    header = pn.Row(
        pn.pane.Markdown(f"### {home_name}", margin=(0, 0, 0, 0)),
        pn.Spacer(),
        pn.pane.Markdown(
            "**Total energy (kWh)**\n\n"
            f"<span style='font-size:28pt; font-weight:600;'>{format_kwh(latest_total)}</span>",
            margin=(0, 0, 0, 0),
        ),
        sizing_mode="stretch_width",
    )

    df_power = compute_power_kW(df_home)

    energy_slider = pn.widgets.DatetimeRangeSlider(
        name="Daily energy period",
        start=start,
        end=end,
        value=(end - pd.Timedelta(days=7), end),
        step=60_000,
        sizing_mode="stretch_width",
    )
    power_slider = pn.widgets.DatetimeRangeSlider(
        name="Power period",
        start=start,
        end=end,
        value=(end - pd.Timedelta(days=7), end),
        step=60_000,
        sizing_mode="stretch_width",
    )

    quick_opts = ["6h", "24h", "7d", "14d", "All"]
    energy_quick = pn.widgets.RadioButtonGroup(
        options=quick_opts, value="7d", button_type="primary", sizing_mode="stretch_width"
    )
    power_quick = pn.widgets.RadioButtonGroup(
        options=quick_opts, value="7d", button_type="primary", sizing_mode="stretch_width"
    )

    energy_quick.param.watch(lambda e: apply_quick_range(e.new, energy_slider, end), "value")
    power_quick.param.watch(lambda e: apply_quick_range(e.new, power_slider, end), "value")

    # Base plot kwargs (no interactive tools)
    PLOT_KW = dict(
        height=260,
        responsive=False,
        tools=[],
        toolbar=None,
        hover=False,
    )

    RANGE_OPTS = dict(framewise=True, axiswise=True, shared_axes=False)
    TOOL_OPTS = dict(default_tools=[], active_tools=[], hooks=[disable_all_tools_hook])

    # --- GRIDLINES: force Bokeh grid objects to be visible and styled ---
    # Bokeh gridline appearance is controlled by properties like grid_line_color/alpha/width/visible. [1](https://docs.bokeh.org/en/latest/docs/reference/models/grids.html)
    # hvPlot supports backend_opts to set backend object properties directly. [2](https://hvplot.holoviz.org/en/docs/latest/ref/plotting_options/styling.html)
    FORCE_GRID_BACKEND_OPTS = dict(
        show_grid=True,
        backend_opts={
            "xgrid.visible": True,
            "ygrid.visible": True,
            "xgrid.grid_line_color": "#d0d0d0",
            "ygrid.grid_line_color": "#d0d0d0",
            "xgrid.grid_line_alpha": 0.35,
            "ygrid.grid_line_alpha": 0.35,
            "xgrid.grid_line_width": 1,
            "ygrid.grid_line_width": 1,
        },
    )

    def _energy_plot(rng):
        lo, hi = map(pd.Timestamp, rng)
        dff = df_home[(df_home.ts_naive >= lo) & (df_home.ts_naive <= hi)]
        if dff.empty:
            return hv.Text(0.5, 0.5, "No data").opts(height=260)

        plot = dff.hvplot.line(
            x="ts_naive",
            y="e_daily",
            color=color,
            line_width=2,
            title="Daily energy (kWh)",
            xlim=(lo.to_pydatetime(), hi.to_pydatetime()),
            **PLOT_KW,
        )
        return plot.opts(**RANGE_OPTS, **TOOL_OPTS, **FORCE_GRID_BACKEND_OPTS)

    def _power_plot(rng):
        lo, hi = map(pd.Timestamp, rng)
        dff = df_power[(df_power.ts_naive >= lo) & (df_power.ts_naive <= hi)]
        if dff.empty:
            return hv.Text(0.5, 0.5, "No data").opts(height=260)

        plot = dff.hvplot.line(
            x="ts_naive",
            y="P_kW",
            color=color,
            line_width=2,
            title="Power (kW)",
            xlim=(lo.to_pydatetime(), hi.to_pydatetime()),
            **PLOT_KW,
        )
        return plot.opts(**RANGE_OPTS, **TOOL_OPTS, **FORCE_GRID_BACKEND_OPTS)

    energy_view = pn.bind(_energy_plot, energy_slider.param.value)
    power_view = pn.bind(_power_plot, power_slider.param.value)

    energy_pane = pn.pane.HoloViews(energy_view, sizing_mode="stretch_width", height=280)
    power_pane = pn.pane.HoloViews(power_view, sizing_mode="stretch_width", height=280)

    energy_section = pn.Column(
        energy_pane,
        energy_quick,
        energy_slider,
        sizing_mode="stretch_width",
        margin=(0, 5, 10, 5),
    )
    power_section = pn.Column(
        power_pane,
        power_quick,
        power_slider,
        sizing_mode="stretch_width",
        margin=(0, 5, 10, 5),
    )

    return pn.Card(
        header,
        energy_section,
        power_section,
        title=home_name,
        collapsed=False,
        sizing_mode="stretch_width",
        margin=(5, 5, 15, 5),
    )

# -------------------------------------------------------------------
# App
# -------------------------------------------------------------------
def make_app():
    df = load_data()

    homes = (
        df[["home_id", "home_name"]]
        .drop_duplicates()
        .sort_values(["home_name", "home_id"])
        .head(2)
    )

    if homes.empty:
        return pn.pane.Markdown("### No homes found in the last 14 days.")

    colors = Category10[10]
    blocks = []

    for i, row in enumerate(homes.itertuples(index=False)):
        df_home = df[df.home_id == row.home_id].copy()
        if not df_home.empty:
            blocks.append(build_home_block(df_home, colors[i]))

    return pn.Column("# Tibber Energy Dashboard", *blocks, sizing_mode="stretch_width")

make_app().servable()
