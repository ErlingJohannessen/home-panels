import panel as pn
import pandas as pd
import datetime as dt
import io
from PIL import Image
from sqlalchemy import create_engine, text
import calendar as calmod
from datetime import date
import base64
import param
import matplotlib.pyplot as plt
import numpy as np
from zoneinfo import ZoneInfo
import os

from astral import Observer
from astral.sun import sun

SOURCE_COORDS = {
    "dell-ubuntu":     (60.4650032, 8.3562666),
    "raspberrypi":     (60.4650032, 8.3562666),
    "hp-ubuntu":       (60.3263938, 5.2859655),
}

def coords_for_source(source: str):
    # Default: return hp-ubuntu coords if unknown source
    return SOURCE_COORDS.get(source, (60.3263938, 5.2859655))


def sunrise_sunset_local(day: date, lat: float, lon: float, tz: ZoneInfo):
    """
    Returns (sunrise_dt_local, sunset_dt_local) timezone-aware datetimes in tz.
    """
    s = sun(Observer(latitude=lat, longitude=lon), date=day, tzinfo=tz)
    return s["sunrise"], s["sunset"]  # tz-aware


def hour_floor(t: dt.datetime) -> dt.datetime:
    return t.replace(minute=0, second=0, microsecond=0)

def hour_ceil(t: dt.datetime) -> dt.datetime:
    if t.minute == 0 and t.second == 0 and t.microsecond == 0:
        return t
    return (t + dt.timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )

def daylight_hour_window(day: date, source: str):
    lat, lon = coords_for_source(source)
    sunrise_dt, sunset_dt = sunrise_sunset_local(day, lat, lon, LOCAL_ZONE)

    start_inclusive = hour_floor(sunrise_dt)
    end_inclusive   = hour_ceil(sunset_dt)

    return (
        start_inclusive.replace(tzinfo=None),
        end_inclusive.replace(tzinfo=None),
        sunrise_dt,
        sunset_dt,
    )
    

    
# ============================================================
# Panel init (ONE call)
# ============================================================

GLOBAL_CSS = """
/* A bit nicer on small screens */
@media (max-width: 768px) {
  h2, h3 { font-size: 1.1rem; }
}

/* Optional: reduce outer padding if any template adds it */
body { margin: 0; }
"""

pn.extension("tabulator", raw_css=[GLOBAL_CSS])

# ============================================================
# Button styling for Shadow DOM (works with Panel/Bokeh widgets)
# ============================================================

HOUR_NAV_SS = """
:host(.hour-nav) .bk-btn,
:host(.hour-nav) .bk-btn-group button,
:host(.hour-nav) button {
  background: #111 !important;
  background-color: #111 !important;
  color: #fff !important;
  border-color: #111 !important;
}
:host(.hour-nav) .bk-btn:hover,
:host(.hour-nav) .bk-btn-group button:hover {
  background: #222 !important;
  background-color: #222 !important;
  color: #fff !important;
}
:host(.hour-nav) .bk-btn:disabled,
:host(.hour-nav) .bk-btn.bk-disabled,
:host(.hour-nav) .bk-btn-group button:disabled,
:host(.hour-nav) .bk-btn-group button.bk-disabled {
  background: #e6e6e6 !important;
  background-color: #e6e6e6 !important;
  color: #999 !important;
  border-color: #d0d0d0 !important;
  opacity: 1 !important;
  cursor: not-allowed !important;
}
"""

# ============================================================
# Timezone helpers
# ============================================================

LOCAL_TZ = "Europe/Oslo"
LOCAL_ZONE = ZoneInfo(LOCAL_TZ)

def epoch_to_local_dt(ts: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(int(ts), tz=LOCAL_ZONE)

def epoch_to_local_str(ts: int, fmt: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    return epoch_to_local_dt(ts).strftime(fmt)

def local_day_to_utc_epoch_range(day: date) -> tuple[int, int]:
    start_local = dt.datetime.combine(day, dt.time(0, 0, 0), tzinfo=LOCAL_ZONE)
    end_local = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, 0, 0), tzinfo=LOCAL_ZONE)
    start_epoch = int(start_local.astimezone(dt.timezone.utc).timestamp())
    end_epoch = int(end_local.astimezone(dt.timezone.utc).timestamp())
    return start_epoch, end_epoch

def format_epoch(ts):
    return epoch_to_local_str(ts)

# ============================================================
# Thumbnail helper
# ============================================================

def thumbnail_from_bytes(raw, max_size=(120, 90)):
    try:
        im = Image.open(io.BytesIO(raw))
        im.thumbnail(max_size)
        buf = io.BytesIO()
        im.save(buf, format="JPEG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return (
            f"<img src='data:image/jpeg;base64,{b64}' "
            "style='max-width:120px; max-height:90px; border-radius:4px; cursor:pointer;'/>"
        )
    except Exception:
        return ""

# ============================================================
# Database (RECOMMENDED: use env vars instead of hardcoding)
# ============================================================

DB_USER = os.getenv("DB_USER", "erling")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Gnilre_22")   # <-- set env var in deployment
DB_HOST = os.getenv("DB_HOST", "www.accretiosolutions.com")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "linuxdatabase")

ENGINE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(ENGINE_URL, pool_pre_ping=True)

# ============================================================
# Queries
# ============================================================

def q_sources():
    sql = "SELECT DISTINCT source FROM public.images ORDER BY source;"
    with engine.connect() as c:
        return [r[0] for r in c.execute(text(sql)).fetchall()]

def q_days(source):
    sql = f"""
    SELECT DISTINCT (to_timestamp(timestamp) AT TIME ZONE '{LOCAL_TZ}')::date AS day_local
    FROM public.images
    WHERE source = :source
    ORDER BY day_local DESC;
    """
    with engine.connect() as c:
        return [r[0] for r in c.execute(text(sql), {"source": source}).fetchall()]

def q_times(source, day):
    start_epoch, end_epoch = local_day_to_utc_epoch_range(day)
    sql = """
    SELECT timestamp
    FROM public.images
    WHERE source = :source
      AND timestamp >= :start_epoch
      AND timestamp <  :end_epoch
    ORDER BY timestamp DESC;
    """
    with engine.connect() as c:
        return [r[0] for r in c.execute(text(sql), {
            "source": source,
            "start_epoch": start_epoch,
            "end_epoch": end_epoch,
        }).fetchall()]

def q_image_bytes(source, ts, image_col="image_data"):
    sql = f"""
    SELECT {image_col}
    FROM public.images
    WHERE source = :source AND timestamp = :ts
    LIMIT 1;
    """
    with engine.connect() as c:
        row = c.execute(text(sql), {"source": source, "ts": int(ts)}).fetchone()
    return None if row is None else row[0]

def q_day_counts_in_month(source, year, month):
    sql = f"""
    SELECT (to_timestamp(timestamp) AT TIME ZONE '{LOCAL_TZ}')::date AS day_local,
           COUNT(*)::int AS n
    FROM public.images
    WHERE source = :source
      AND EXTRACT(YEAR  FROM (to_timestamp(timestamp) AT TIME ZONE '{LOCAL_TZ}')) = :year
      AND EXTRACT(MONTH FROM (to_timestamp(timestamp) AT TIME ZONE '{LOCAL_TZ}')) = :month
    GROUP BY day_local
    ORDER BY day_local;
    """
    with engine.connect() as c:
        rows = c.execute(text(sql), {"source": source, "year": int(year), "month": int(month)}).fetchall()
    return {row[0]: int(row[1]) for row in rows}

def q_last10_with_thumbs(source, day, image_col="image_data"):
    start_epoch, end_epoch = local_day_to_utc_epoch_range(day)
    sql = f"""
    SELECT timestamp AS ts, {image_col} AS img
    FROM public.images
    WHERE source = :source
      AND timestamp >= :start_epoch
      AND timestamp <  :end_epoch
    ORDER BY timestamp DESC
    LIMIT 10;
    """
    with engine.connect() as c:
        rows = c.execute(text(sql), {
            "source": source,
            "start_epoch": start_epoch,
            "end_epoch": end_epoch,
        }).fetchall()

    if not rows:
        return pd.DataFrame(columns=["When", "Preview", "_ts"])

    ts_list, img_bytes = zip(*rows)
    return pd.DataFrame({
        "When": [epoch_to_local_str(ts) for ts in ts_list],
        "Preview": [thumbnail_from_bytes(b) for b in img_bytes],
        "_ts": [int(ts) for ts in ts_list],
    }).reset_index(drop=True)

def q_hourly_daylight_window(source, day, image_col="image_data"):
    """
    One row per LOCAL hour bucket for the given local day, but only between:
      last hour before sunrise  -> hour after sunset (inclusive)
    """
    # Compute overall day bounds (UTC epoch) for DB filtering
    start_epoch, end_epoch = local_day_to_utc_epoch_range(day)

    # Compute daylight hour window in LOCAL (naive) timestamps
    start_local_naive, end_local_naive, sunrise_dt, sunset_dt = daylight_hour_window(day, source)

    sql = f"""
    WITH x AS (
      SELECT
        timestamp AS ts_utc,
        {image_col} AS img,
        (to_timestamp(timestamp) AT TIME ZONE '{LOCAL_TZ}') AS ts_local,
        date_trunc('hour', (to_timestamp(timestamp) AT TIME ZONE '{LOCAL_TZ}')) AS hour_bucket_local
      FROM public.images
      WHERE source = :source
        AND timestamp >= :start_epoch
        AND timestamp <  :end_epoch
        AND (to_timestamp(timestamp) AT TIME ZONE '{LOCAL_TZ}') >= :start_local
        AND (to_timestamp(timestamp) AT TIME ZONE '{LOCAL_TZ}') <=  :end_local
    )
    SELECT DISTINCT ON (hour_bucket_local)
      ts_utc,
      hour_bucket_local,
      img
    FROM x
    ORDER BY
      hour_bucket_local,
      CASE WHEN ts_local = hour_bucket_local THEN 0 ELSE 1 END,
      ts_local ASC;
    """

    with engine.connect() as c:
        rows = c.execute(text(sql), {
            "source": source,
            "start_epoch": start_epoch,
            "end_epoch": end_epoch,
            "start_local": start_local_naive,
            "end_local": end_local_naive,
        }).fetchall()

    if not rows:
        # Optional: show sunrise/sunset info even when empty
        return pd.DataFrame(columns=["Hour", "Preview", "_ts"])

    ts_list, hour_bucket_list, img_bytes = zip(*rows)

    hour_labels = []
    for ts in ts_list:
        h = epoch_to_local_dt(ts).replace(minute=0, second=0, microsecond=0)
        hour_labels.append(h.strftime("%Y-%m-%d %H:00 %Z"))

    df = pd.DataFrame({
        "Hour": hour_labels,
        "Preview": [thumbnail_from_bytes(b) for b in img_bytes],
        "_ts": [int(ts) for ts in ts_list],
    }).reset_index(drop=True)

    return df

# ============================================================
# Heatmaps (unchanged)
# ============================================================

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def q_month_counts(source):
    sql = f"""
    SELECT EXTRACT(MONTH FROM (to_timestamp(timestamp) AT TIME ZONE '{LOCAL_TZ}'))::int AS month,
           COUNT(*)::int AS n
    FROM public.images
    WHERE source = :source
    GROUP BY month
    ORDER BY month;
    """
    with engine.connect() as c:
        rows = c.execute(text(sql), {"source": source}).fetchall()
    return pd.DataFrame(rows, columns=["month", "n"])

def q_yearmonth_counts(source):
    sql = f"""
    SELECT date_trunc('month', (to_timestamp(timestamp) AT TIME ZONE '{LOCAL_TZ}'))::date AS ym,
           COUNT(*)::int AS n
    FROM public.images
    WHERE source = :source
    GROUP BY ym
    ORDER BY ym;
    """
    with engine.connect() as c:
        rows = c.execute(text(sql), {"source": source}).fetchall()
    return pd.DataFrame(rows, columns=["ym", "n"])

def heatmap_pane_from_series(index_labels, values, title, xlabel):
    data = np.array(values, dtype=float)[None, :]
    fig, ax = plt.subplots(figsize=(10, 2.4))
    im = ax.imshow(data, aspect="auto")
    ax.set_title(title, pad=6)
    ax.set_xlabel(xlabel)
    ax.set_yticks([0])
    ax.set_yticklabels([""])
    ax.set_xticks(np.arange(len(index_labels)))
    ax.set_xticklabels(index_labels, rotation=45, ha="right")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Images")
    fig.tight_layout()
    
    return pn.pane.Matplotlib(
        fig,
        tight=True,
        sizing_mode="stretch_width",
        max_height=180,   # ✅ limits reserved space
        margin=0,
    )


def seasonality_heatmap_for_source(source):
    df = q_month_counts(source)
    month_to_count = {int(m): int(n) for m, n in zip(df["month"], df["n"])}
    labels = MONTH_NAMES
    values = [month_to_count.get(m, 0) for m in range(1, 13)]
    return heatmap_pane_from_series(labels, values, f"Images for {source} by month (seasonality)", "Month")

def timeline_heatmap_for_source(source):
    df = q_yearmonth_counts(source)
    if df.empty:
        return pn.pane.Markdown("_No data_")
    labels = [pd.to_datetime(d).strftime("%Y-%m") for d in df["ym"]]
    values = df["n"].astype(int).tolist()
    return heatmap_pane_from_series(labels, values, f"Images for {source} by year-month", "Year-Month")

# ============================================================
# Shared selection across source tabs
# ============================================================

class SharedSelection(param.Parameterized):
    day  = param.Date(default=None)
    time = param.Integer(default=None)  # UTC epoch seconds

shared = SharedSelection()

# ============================================================
# UI State (IMPORTANT: this makes pn.depends reliable)
# ============================================================

class UIState(param.Parameterized):
    controls_visible = param.Boolean(default=False)

# ============================================================
# App per source
# ============================================================

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def make_source_app(source, shared):
    ui = UIState()  # per tab state

    day_w = pn.widgets.Select(name="Date", options=[])
    time_w = pn.widgets.Select(name="Time", options={})

    _sync = {"flag": False}
    _updating = {"flag": False}

    # ---- watchers for shared selection ----
    def on_day_selected(event):
        if _sync["flag"]:
            return
        shared.day = event.new

    def on_time_selected(event):
        if _sync["flag"]:
            return
        shared.time = event.new

    day_w.param.watch(on_day_selected, "value")
    time_w.param.watch(on_time_selected, "value")

    # ---- calendar widgets ----
    year_w = pn.widgets.IntInput(name="Year", value=dt.datetime.utcnow().year, start=2000, end=2100, width=120)
    month_w = pn.widgets.Select(name="Month",
                               options={calmod.month_name[m]: m for m in range(1, 13)},
                               value=dt.datetime.utcnow().month,
                               width=160)

    # ---- tables ----
    hourly_tbl = pn.widgets.Tabulator(
        height=300,
        show_index=False,
        selectable=1,
        formatters={"Preview": "html"},
        configuration={
            "columns": [
                {"title": "Hour", "field": "Hour"},
                {"title": "Preview", "field": "Preview", "formatter": "html", "editable": False},
                {"title": "_ts", "field": "_ts", "visible": False},
            ],
        },
        sizing_mode="stretch_width",
    )

    # ---- heatmaps ----
    heatmap_tabs = pn.Tabs(
        ("Seasonality (Month)", pn.panel(lambda: seasonality_heatmap_for_source(source))),
        ("Timeline (Year-Month)", pn.panel(lambda: timeline_heatmap_for_source(source))),
        sizing_mode="stretch_width",
        margin=0,
    )


    # ---- refresh days/times ----
    def refresh_days_and_times(reason=""):
        if _updating["flag"]:
            return
        _updating["flag"] = True
        try:
            prev_day = day_w.value
            prev_time = time_w.value

            days = q_days(source)
            day_w.options = days
            day_w.value = prev_day if prev_day in days else (days[0] if days else None)

            selected_day = day_w.value

            if not day_w.value:
                time_w.options = {}
                time_w.value = None
                return

            times = q_times(source, day_w.value)
            if not times:
                time_w.options = {}
                time_w.value = None
                return

            options = {format_epoch(ts): ts for ts in times}
            time_w.options = options

            now_local = dt.datetime.now(LOCAL_ZONE)
            now_epoch = int(now_local.timestamp())
            
            # times is DESCENDING (latest first)
            candidates = []
            
            # Prefer images between sunrise and now
            if selected_day == now_local.date():
                lat, lon = coords_for_source(source)
                sunrise_dt, sunset_dt = sunrise_sunset_local(selected_day, lat, lon, LOCAL_ZONE)
                sunrise_epoch = int(sunrise_dt.timestamp())
            
                candidates = [
                    t for t in times
                    if sunrise_epoch <= t <= now_epoch
                ]
            
            # Fallbacks
            if not candidates:
                candidates = times
            
            # Pick the most recent valid image
            time_w.value = candidates[0] if candidates else None
        finally:
            _updating["flag"] = False

    def apply_shared_to_this_tab(reason="shared changed"):
        if _sync["flag"]:
            return
        _sync["flag"] = True
        try:
            if not day_w.options:
                day_w.options = q_days(source)

            if shared.day and shared.day in day_w.options:
                day_w.value = shared.day

            refresh_days_and_times(reason)

            if shared.time and shared.time in time_w.options.values():
                time_w.value = shared.time
        finally:
            _sync["flag"] = False

    shared.param.watch(lambda e: apply_shared_to_this_tab("shared day changed"), "day")
    shared.param.watch(lambda e: apply_shared_to_this_tab("shared time changed"), "time")

    day_w.param.watch(lambda e: refresh_days_and_times("day changed"), "value")

    # ---- clicks on tables ----

    def on_hourly_click(event):
        if event.column != "Preview":
            return
        df = hourly_tbl.value
        if df is None or df.empty:
            return
        time_w.value = int(df.iloc[event.row]["_ts"])

    hourly_tbl.on_click(on_hourly_click)

    # ---- calendar view ----
    @pn.depends(year_w.param.value, month_w.param.value)
    def calendar_view(year, month):
        year = int(year)
        month = int(month)
        counts = q_day_counts_in_month(source, year, month)
        cal = calmod.Calendar(firstweekday=0)
        weeks = cal.monthdatescalendar(year, month)

        grid = pn.GridSpec(sizing_mode="stretch_width", max_width=420)

        for i, wd in enumerate(WEEKDAYS):
            grid[0, i] = pn.pane.Markdown(f"**{wd}**", align="center")

        for r, week in enumerate(weeks, start=1):
            for c, d in enumerate(week):
                in_month = (d.month == month)
                n = counts.get(d, 0)

                btn = pn.widgets.Button(
                    name=str(d.day),
                    button_type=("warning" if (in_month and n > 0) else "light"),
                    disabled=not in_month,
                    width=52,
                    height=38,
                    margin=1,
                )

                if in_month and n > 0:
                    btn.tooltip = f"{n} image(s)"
                    btn.on_click(lambda ev, selected_date=d: setattr(day_w, "value", selected_date))

                grid[r, c] = btn

        return pn.Column(pn.Row(year_w, month_w, sizing_mode="stretch_width"), grid)

    # ---- day panel (tables) ----
    @pn.depends(day_w.param.value)
    def d_panel(day):
        if not day:
            hourly_tbl.value = pd.DataFrame()
            return pn.Column(
                pn.pane.Markdown("_Select a date to see images_"),
                hourly_tbl,
                sizing_mode="stretch_width",
            )
    
        # Populate hourly daylight table
        df = q_hourly_daylight_window(source, day)
        hourly_tbl.value = df

    
        # ✅ Auto-select the middle image (if available)
        if not df.empty:
            mid = len(df) // 2

            hourly_tbl.selection = [mid]     # triggers the JS callback => scrolls to row
            time_w.value = int(df.iloc[mid]["_ts"])

            ts_mid = int(df.iloc[mid]["_ts"])
    
            # Set selected image ONLY if time is not already valid for this day
            if time_w.value not in df["_ts"].values:
                time_w.value = ts_mid
    
            # Optional: visually select the row in Tabulator
            hourly_tbl.selection = [mid]
    
        # Sunrise / sunset info (as you already have)
        start_local, end_local, sunrise_dt, sunset_dt = daylight_hour_window(day, source)
    
        info = pn.pane.Markdown(
            f"**Sunrise:** {sunrise_dt.strftime('%H:%M %Z')}  \n"
            f"**Sunset:** {sunset_dt.strftime('%H:%M %Z')}  \n"
            f"_Showing hours from {start_local.strftime('%H:%M')} to {end_local.strftime('%H:%M')}_",
            sizing_mode="stretch_width",
        )
    
        return pn.Column(
            info,
            "### This day, hourly",
            hourly_tbl,
            sizing_mode="stretch_width",
        )  
     # ---- navigation helpers ----
    def get_day_times_and_index():
        if not day_w.value or not time_w.value:
            return [], None
        times = q_times(source, day_w.value)
        if not times:
            return [], None
        try:
            idx = times.index(time_w.value)
        except ValueError:
            return times, None
        return times, idx

    def find_time_at_least_one_hour_away(times_desc, current_ts, direction):
        if current_ts is None:
            return None
        target = int(current_ts) + (3600 * direction)
        times_asc = sorted(int(t) for t in times_desc)
        if direction == -1:
            candidates = [t for t in times_asc if t <= target]
            return candidates[-1] if candidates else None
        else:
            candidates = [t for t in times_asc if t >= target]
            return candidates[0] if candidates else None

    # ---- main render ----
    @pn.depends(time_w.param.value, day_w.param.value)
    def render_main(ts, day):
        ui.controls_visible = False   # 👈 AUTO‑HIDE CONTROLS
        if not (day and ts):
            return pn.Column("Select Date and Time", sizing_mode="stretch_width")

        raw = q_image_bytes(source, ts)
        if raw is None:
            return pn.pane.Markdown("No image found")

        im = Image.open(io.BytesIO(raw))
        ts_local = dt.datetime.fromtimestamp(int(ts), tz=ZoneInfo("Europe/Oslo"))

        times, idx = get_day_times_and_index()
        has_prev = idx is not None and idx < len(times) - 1
        has_next = idx is not None and idx > 0

        minus_1h_ts = find_time_at_least_one_hour_away(times, ts, direction=-1)
        plus_1h_ts  = find_time_at_least_one_hour_away(times, ts, direction=+1)

        prev_btn = pn.widgets.Button(name="◀ Previous", button_type="primary", disabled=not has_prev, width=120)
        next_btn = pn.widgets.Button(name="Next ▶", button_type="primary", disabled=not has_next, width=120)

        minus_1h_btn = pn.widgets.Button(
            name="−1 hour", button_type="default", button_style="solid",
            disabled=(minus_1h_ts is None), width=100,
            css_classes=["hour-nav"], stylesheets=[HOUR_NAV_SS]
        )

        plus_1h_btn = pn.widgets.Button(
            name="+1 hour", button_type="default", button_style="solid",
            disabled=(plus_1h_ts is None), width=100,
            css_classes=["hour-nav"], stylesheets=[HOUR_NAV_SS]
        )

        prev_btn.on_click(lambda ev: setattr(time_w, "value", times[idx + 1]) if has_prev else None)
        next_btn.on_click(lambda ev: setattr(time_w, "value", times[idx - 1]) if has_next else None)
        minus_1h_btn.on_click(lambda ev: setattr(time_w, "value", int(minus_1h_ts)) if minus_1h_ts else None)
        plus_1h_btn.on_click(lambda ev: setattr(time_w, "value", int(plus_1h_ts)) if plus_1h_ts else None)

        nav_row = pn.Row(
            pn.layout.HSpacer(),
            prev_btn, next_btn,
            pn.Spacer(width=12),
            minus_1h_btn, plus_1h_btn,
            pn.layout.HSpacer(),
            sizing_mode="stretch_width",
        )

        info = pn.pane.Markdown(
            f"""
<div style="text-align:center">
  <b>Source:</b> <code>{source}</code><br>
  <b>Timestamp (local):</b> {ts_local.strftime('%Y-%m-%d %H:%M:%S %Z')}
</div>
""",
            sizing_mode="stretch_width",
            margin=(6, 0, 10, 0),
        )

        img = pn.pane.Image(
            im,
            sizing_mode="stretch_width",
            styles={
                "object-fit": "contain",
                "max-height": "70vh",
                "width": "100%",
                "display": "block",
                "margin": "0 auto",
            },
        )

        return pn.Column(
            info,
            img,
            nav_row,
            sizing_mode="stretch_width",
            max_width=1200,
        )

    # ============================================================
    # Sidebar content (will be shown as floating overlay)
    # ============================================================

    sidebar = pn.Column(
        f"## Image Browser — `{source}`",
        calendar_view,
        day_w,
        time_w,
        "### Image availability",
        heatmap_tabs,
        d_panel,
        sizing_mode="stretch_width",
        max_width=360,
        margin=(0, 5, 0, 5),
    )

    # ============================================================
    # Floating controls overlay (no Accordion/Tabs)
    # ============================================================

    toggle_controls_btn = pn.widgets.Button(name="⚙ Controls", button_type="default", width=120)
    toggle_controls_btn.styles = {
        "position": "fixed",
        "top": "12px",
        "right": "12px",
        "z-index": "1100",
    }

    close_btn = pn.widgets.Button(name="✕", button_type="light", width=36, height=32)
    close_btn.styles = {"float": "right"}

    def toggle_controls(event):
        ui.controls_visible = not ui.controls_visible

    def close_controls(event):
        ui.controls_visible = False

    toggle_controls_btn.on_click(toggle_controls)
    close_btn.on_click(close_controls)


    @pn.depends(ui.param.controls_visible)
    def floating_controls(show):
        if not show:
            return pn.Spacer(height=0)
    
        return pn.Column(
            sidebar,
            styles={
                "position": "fixed",
    
                # ✅ Mobile-safe anchoring
                "top": "0",
                "right": "0",
                "left": "0",
    
                # ✅ Use dynamic viewport height (better on iOS)
                "height": "100dvh",
                "max-height": "100dvh",
    
                # ✅ Scroll inside panel
                "overflow-y": "auto",
                "overflow-x": "hidden",
    
                # ✅ Visual polish
                "background": "white",
                "box-shadow": "0 6px 20px rgba(0,0,0,0.25)",
                "z-index": "1000",
                "padding": "12px",
            },
            sizing_mode="stretch_width",
        )
    

    # Init
    _sync["flag"] = True
    refresh_days_and_times("init")
    _sync["flag"] = False
    apply_shared_to_this_tab("initial sync")

    # Final layout: image first, overlay controls + floating button
    main = pn.Column(render_main, sizing_mode="stretch_width")
    return pn.Column(toggle_controls_btn, main, floating_controls, sizing_mode="stretch_width")

# ============================================================
# Build tabs per source (your existing pattern)
# ============================================================

sources = q_sources()

source_tabs = pn.Tabs(
    *[(src, make_source_app(src, shared)) for src in sources],
    dynamic=True,
    sizing_mode="stretch_both",
)

source_tabs.servable()

