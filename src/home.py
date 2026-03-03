import panel as pn

pn.extension(design="material")

TITLE = "Management Dashboard"

DESCRIPTION = """
Welcome to the management dashboard.

Select one of the applications below:
"""

apps = [
    ("🚗 Vehicle Map", "./vehiclemap"),
    ("🖼️ Image Viewer", "./imageviewer"),
    #("📊 Charts", "./charts"),
]

def app_card(title, link):
    return pn.Column(
        pn.pane.Markdown(f"### {title}"),
        pn.pane.Markdown(f"[Open]({link})"),
        styles={
            "border": "1px solid #ddd",
            "border-radius": "8px",
            "padding": "16px",
            "background": "white",
        },
        sizing_mode="stretch_width",
    )

cards = pn.GridSpec(sizing_mode="stretch_width", max_width=900)

for i, (title, link) in enumerate(apps):
    cards[i // 2, i % 2] = app_card(title, link)

pn.Column(
    pn.pane.Markdown(f"# {TITLE}"),
    pn.pane.Markdown(DESCRIPTION),
    pn.Spacer(height=10),
    cards,
    sizing_mode="stretch_width",
    max_width=1000,
).servable()
