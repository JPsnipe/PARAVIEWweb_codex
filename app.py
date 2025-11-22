import math
import random
import threading

import plotly.graph_objects as go
from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vtk as vtk_widgets, vuetify3 as vuetify
from trame.widgets.plotly import Figure

from pipeline import CASE_VARIANTS, FurnacePipeline

# Inline ArcelorMittal logo (light) to avoid extra assets
LOGO_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAU8AAABTCAMAAADr6I76AAAAY1BMVEVHcEz///8AAABaWlo6OjqSkpK9vb3V1dXk5OTo6OipsbG+vr6Li4uysrLV"
    "1dXu7u5jY2P39/eKioqGhoZ/f3+Pj4+3t7enn59JSUnExMR5eXmUlJR9fX2jo6PKyspTU1PKX0b0AAADQklEQVR4nO2diZaqMBBFO7RQNJ1pi73X"
    "pP//KxkEh6TAoydn5bxmDVLcmc4YNsrXtXJFGf4ZtlVVVVVVVVVVVVVVVVVVVVVVVVVVVX1sN7o/QG+qN6cHVdmj4QZrjFHkDviPbnTTLn3QJ+Q6z"
    "PbnXz7qBfIfpUMcNQ7t1x1+UtuUdqMo1hxp1hxp1hxp1hxp1hxp1hxp1hxp1hxp1hxp1hxp1hxj2PYt6o8w2H+Qu7dx0x+MfZy7s0cUuDka8g3xD7"
    "Mw5cdYj6i9hx1iPqL2HHWI+ovYcdYj6i9hx1iPqL2HHWI+ovYcdYj6i9hx1iPqL2HHWI+ovYcdYj6i9h21i3oj7PfBt6o8g3wHu3cdMfRP2cu7NHF"
    "LgzGvIu8Q+zMOXHWI+ovYcdYj6i9hx1iPqL2HHWI+ovYcdYj6i9hx1iPqL2HHWI+ovYcdYj6i9hx1iPqL2HHWI+ovYcdYj6i9hx1iPqL2Hf6DXsH5"
    "L7O7q5x7k7Z8+H3q7wrcW5Hn1+VHUR9R+qn6D6ifpHpH9QdYfRD1B9QPUP1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QP"
    "UD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1H9uKn6C6ifpHpH9QPUP1D9QNVP1D1Q9QPUD1D9QdYfRD1B9QPUP1D9QPUD1D"
    "9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUP1H6iefqL6ieofoHpH1B9QPUbRD1B9QPUP1D9Q"
    "PUbRD1B9QPUP1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1D9QPUD1H9v13H/EOGDJu+AAAAAElFTkSuQmCC"
)

# Debug namespace key issues (unexpected non-string keys)
# Note: all state keys must be strings; avoid binding dicts directly

server = get_server(name="blast_furnace_monitor", client_type="vue3")
state, ctrl = server.state, server.controller

pipeline = FurnacePipeline()
ctrl.view_update = lambda *_, **__: None

# --------------------------------------------------------------------------- #
# State defaults
# --------------------------------------------------------------------------- #
state.case_name = pipeline.case_name
state.temperature_iso = 800.0
state.shell_opacity = 0.9
state.clip_enabled = False
state.clip_axis = "Z"

xmin, xmax, ymin, ymax, zmin, zmax = pipeline.bounds
state.clip_x = (xmin + xmax) * 0.5
state.clip_y = (ymin + ymax) * 0.5
state.clip_z = (zmin + zmax) * 0.5
state.clip_x_min, state.clip_x_max = xmin, xmax
state.clip_y_min, state.clip_y_max = ymin, ymax
state.clip_z_min, state.clip_z_max = zmin, zmax

state.probe_label = "Click on the furnace to probe temperature"
state.case_items = list(CASE_VARIANTS.keys())
state.material_table = pipeline.material_table
state.block_table = pipeline.block_table
state.material_headers = [
    {"text": "ID", "value": "id", "width": 50},
    {"text": "Name", "value": "name"},
    {"text": "k (W/mK)", "value": "k", "width": 90},
    {"text": "ρ (kg/m3)", "value": "rho", "width": 90},
]
state.block_headers = [
    {"text": "#", "value": "id", "width": 40},
    {"text": "Zone", "value": "name"},
    {"text": "Band", "value": "band", "width": 90},
    {"text": "Layer", "value": "layer", "width": 90},
    {"text": "Mat", "value": "material", "width": 110},
    {"text": "Tavg", "value": "t_avg", "width": 70},
    {"text": "Tmin", "value": "t_min", "width": 70},
    {"text": "Tmax", "value": "t_max", "width": 70},
]
state.visible_blocks = [entry["id"] for entry in pipeline.block_definitions]
state.active_block_id = None
state.active_block_label = "Selecciona un bloque para ver detalles"
state.show_case = True
state.show_visualization = True
state.show_clip = True
state.show_probe = True
state.show_chart = True
state.show_materials = True
state.show_blocks_table = True
state.show_block_manager = True
pipeline.set_block_visibility(state.visible_blocks)

# --------------------------------------------------------------------------- #
# Chart helpers
# --------------------------------------------------------------------------- #
WINDOW = 60
state.chart_times = list(range(WINDOW))
state.chart_sim = [1150 + 30 * math.sin(i / 9.0) for i in state.chart_times]
state.chart_sensor = [value + random.uniform(-5, 5) for value in state.chart_sim]
chart_widget = None


def build_chart(x, sim, sensor):
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=sim,
            mode="lines",
            name="Simulated Probe A",
            line=dict(color="#ef8a17", width=3),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=sensor,
            mode="lines+markers",
            name="Live Sensor A",
            line=dict(color="#00bcd4", width=2),
            marker=dict(size=5),
        )
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        template="plotly_dark",
        height=240,
        legend=dict(orientation="h", y=1.05, x=0),
        xaxis_title="Time (a.u.)",
        yaxis_title="Temperature (deg C)",
    )
    return fig


def update_chart():
    # Advance a simple random walk for the live sensor
    last_sensor = state.chart_sensor[-1]
    drift = random.uniform(-6, 6)
    updated_sensor = state.chart_sensor[1:] + [last_sensor + drift]

    next_t = state.chart_times[-1] + 1
    updated_time = state.chart_times[1:] + [next_t]

    # Simulated line stays steady for comparison
    updated_sim = state.chart_sim[1:] + [state.chart_sim[-1]]

    state.chart_sensor = updated_sensor
    state.chart_times = updated_time
    state.chart_sim = updated_sim
    if chart_widget:
        chart_widget.update(plotly_fig=build_chart(updated_time, updated_sim, updated_sensor))


# Use trame's periodic callback when available, otherwise fall back to a timer.
def _start_chart_timer():
    def _tick():
        update_chart()
        timer = threading.Timer(1.0, _tick)
        timer.daemon = True
        timer.start()

    _tick()


# --------------------------------------------------------------------------- #
# Callbacks
# --------------------------------------------------------------------------- #
@state.change("temperature_iso")
def on_iso_change(temperature_iso, **_):
    pipeline.update_iso_value(temperature_iso)
    ctrl.view_update()


@state.change("shell_opacity")
def on_opacity_change(shell_opacity, **_):
    pipeline.update_opacity(shell_opacity)
    ctrl.view_update()


@state.change("clip_enabled", "clip_axis", "clip_x", "clip_y", "clip_z")
def on_clip_change(clip_enabled, clip_axis, clip_x, clip_y, clip_z, **_):
    pipeline.update_clip(clip_enabled, clip_axis, clip_x, clip_y, clip_z)
    ctrl.view_update()


def _update_active_block_label():
    try:
        target_id = int(state.active_block_id) if state.active_block_id is not None else None
    except (TypeError, ValueError):
        target_id = state.active_block_id

    details = next((item for item in state.block_table if item.get("id") == target_id), None)
    if details:
        state.active_block_label = (
            f"{details['name']} | {details['material']} | Avg {details['t_avg']} | Min {details['t_min']} | Max {details['t_max']}"
        )
    else:
        state.active_block_label = "Selecciona un bloque para ver detalles"


@state.change("visible_blocks")
def on_visible_blocks_change(visible_blocks, **_):
    pipeline.set_block_visibility(visible_blocks)
    ctrl.view_update()


@state.change("active_block_id")
def on_active_block_change(active_block_id, **_):
    _update_active_block_label()


@state.change("case_name")
def on_case_change(case_name, **_):
    pipeline.update_case(case_name)
    xmin, xmax, ymin, ymax, zmin, zmax = pipeline.bounds
    state.clip_x = (xmin + xmax) * 0.5
    state.clip_y = (ymin + ymax) * 0.5
    state.clip_z = (zmin + zmax) * 0.5
    state.clip_x_min = xmin
    state.clip_x_max = xmax
    state.clip_y_min = ymin
    state.clip_y_max = ymax
    state.clip_z_min = zmin
    state.clip_z_max = zmax
    state.material_table = pipeline.material_table
    state.block_table = pipeline.block_table
    pipeline.set_block_visibility(state.visible_blocks)
    _update_active_block_label()
    ctrl.view_update()


def on_reset_camera():
    pipeline.reset_camera()
    ctrl.view_update()


def on_probe(**kwargs):
    x = kwargs.get("x") or kwargs.get("position", [None, None])[0]
    y = kwargs.get("y") or kwargs.get("position", [None, None])[1]
    info = pipeline.pick(x, y)
    if info:
        block_label = f", block {info['block_id']}" if info.get("block_id") else ""
        state.probe_label = (
            f"Node {info['point_id']}: {info['temperature']} deg C (mat {info.get('material_id')}{block_label}) at {info['position']}"
        )
    else:
        state.probe_label = "No hit (try another spot)"


def on_orbit(direction):
    step = 10.0
    if direction == "left":
        pipeline.camera_orbit(azimuth=-step)
    elif direction == "right":
        pipeline.camera_orbit(azimuth=step)
    elif direction == "up":
        pipeline.camera_orbit(elevation=step)
    elif direction == "down":
        pipeline.camera_orbit(elevation=-step)
    ctrl.view_update()


def on_zoom(factor):
    pipeline.camera_zoom(factor)
    ctrl.view_update()


def on_pan(dx=0.0, dy=0.0):
    pipeline.camera_pan(dx, dy)
    ctrl.view_update()


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
with SinglePageLayout(server) as layout:
    layout.title.set_text("Blast Furnace Thermal Watch (Trame prototype)")

    with layout.toolbar:
        vuetify.VImg(src=LOGO_DATA_URI, max_height=40, max_width=140, contain=True, class_="mr-4")
        vuetify.VBtn(
            "Reset Camera",
            icon="mdi-crosshairs-gps",
            click=on_reset_camera,
            outlined=True,
            dense=True,
            color="#e15200",
        )
        vuetify.VBtn(icon="mdi-undo-variant", dense=True, title="Orbit Left", color="#e15200", click=lambda *_: on_orbit("left"))
        vuetify.VBtn(icon="mdi-redo-variant", dense=True, title="Orbit Right", color="#e15200", click=lambda *_: on_orbit("right"))
        vuetify.VBtn(icon="mdi-arrow-up-bold", dense=True, title="Orbit Up", color="#e15200", click=lambda *_: on_orbit("up"))
        vuetify.VBtn(icon="mdi-arrow-down-bold", dense=True, title="Orbit Down", color="#e15200", click=lambda *_: on_orbit("down"))
        vuetify.VBtn(icon="mdi-magnify-plus", dense=True, title="Zoom In", color="#e15200", click=lambda *_: on_zoom(1.2))
        vuetify.VBtn(icon="mdi-magnify-minus", dense=True, title="Zoom Out", color="#e15200", click=lambda *_: on_zoom(0.8))
        vuetify.VBtn(icon="mdi-cursor-move", dense=True, title="Pan Up", color="#e15200", click=lambda *_: on_pan(0, 1))
        vuetify.VBtn(icon="mdi-cursor-move", dense=True, title="Pan Down", class_="rotate-180", color="#e15200", click=lambda *_: on_pan(0, -1))
        vuetify.VSpacer()
        vuetify.VChip("Desarrollado por SDEA Solutions", small=True, outlined=True, color="#e15200", text_color="#e15200")

    with layout.content:
        with vuetify.VContainer(fluid=True, class_="fill-height pa-0", style="background-color: #f5f5f5;"):
            with vuetify.VRow(no_gutters=True, class_="fill-height"):
                with vuetify.VCol(cols=12, md=4, lg=3, class_="pa-2", style="max-width: 360px;"):
                    with vuetify.VSheet(class_="pa-3", elevation=2, style="background-color: #0f1118; border-left: 4px solid #e15200;"):
                        with vuetify.VCard(flat=True, class_="mb-3"):
                            vuetify.VCardTitle(
                                class_="d-flex align-center",
                                children=[
                                    "Simulation Case",
                                    vuetify.VSpacer(),
                                    vuetify.VBtn(
                                        icon=("show_case ? 'mdi-chevron-up' : 'mdi-chevron-down'",),
                                        variant="text",
                                        density="comfortable",
                                        click=lambda *_: setattr(state, "show_case", not state.show_case),
                                    ),
                                ],
                            )
                            with vuetify.VExpandTransition():
                                with vuetify.VCardText(v_show=("show_case", state.show_case)):
                                    vuetify.VSelect(
                                        v_model=("case_name", state.case_name),
                                        items=("case_items", state.case_items),
                                        density="comfortable",
                                        hide_details=True,
                                        variant="outlined",
                                    )

                        with vuetify.VCard(flat=True, class_="mb-3"):
                            vuetify.VCardTitle(
                                class_="d-flex align-center",
                                children=[
                                    "Visualization",
                                    vuetify.VSpacer(),
                                    vuetify.VBtn(
                                        icon=("show_visualization ? 'mdi-chevron-up' : 'mdi-chevron-down'",),
                                        variant="text",
                                        density="comfortable",
                                        click=lambda *_: setattr(state, "show_visualization", not state.show_visualization),
                                    ),
                                ],
                            )
                            with vuetify.VExpandTransition():
                                with vuetify.VCardText(v_show=("show_visualization", state.show_visualization)):
                                    vuetify.VSlider(
                                        label="Isotherm (deg C)",
                                        v_model=("temperature_iso", state.temperature_iso),
                                        min=pipeline.color_range[0],
                                        max=pipeline.color_range[1],
                                        step=10,
                                        density="comfortable",
                                        hide_details=False,
                                    )
                                    vuetify.VSlider(
                                        label="Shell Opacity",
                                        v_model=("shell_opacity", state.shell_opacity),
                                        min=0.1,
                                        max=1.0,
                                        step=0.05,
                                        density="comfortable",
                                        hide_details=False,
                                    )

                        with vuetify.VCard(flat=True, class_="mb-3"):
                            vuetify.VCardTitle(
                                class_="d-flex align-center",
                                children=[
                                    "Cut Plane",
                                    vuetify.VSpacer(),
                                    vuetify.VBtn(
                                        icon=("show_clip ? 'mdi-chevron-up' : 'mdi-chevron-down'",),
                                        variant="text",
                                        density="comfortable",
                                        click=lambda *_: setattr(state, "show_clip", not state.show_clip),
                                    ),
                                ],
                            )
                            with vuetify.VExpandTransition():
                                with vuetify.VCardText(v_show=("show_clip", state.show_clip)):
                                    vuetify.VSwitch(
                                        label="Enable",
                                        inset=True,
                                        v_model=("clip_enabled", state.clip_enabled),
                                    )
                                    vuetify.VSelect(
                                        label="Axis",
                                        items=["X", "Y", "Z"],
                                        v_model=("clip_axis", state.clip_axis),
                                        density="comfortable",
                                        hide_details=True,
                                        variant="outlined",
                                        disabled=("!clip_enabled",),
                                    )
                                    vuetify.VSlider(
                                        label="X Offset",
                                        v_model=("clip_x", state.clip_x),
                                        min=("clip_x_min", state.clip_x_min),
                                        max=("clip_x_max", state.clip_x_max),
                                        step=0.05,
                                        density="comfortable",
                                        hide_details=False,
                                        disabled=("!clip_enabled",),
                                    )
                                    vuetify.VSlider(
                                        label="Y Offset",
                                        v_model=("clip_y", state.clip_y),
                                        min=("clip_y_min", state.clip_y_min),
                                        max=("clip_y_max", state.clip_y_max),
                                        step=0.05,
                                        density="comfortable",
                                        hide_details=False,
                                        disabled=("!clip_enabled",),
                                    )
                                    vuetify.VSlider(
                                        label="Z Offset",
                                        v_model=("clip_z", state.clip_z),
                                        min=("clip_z_min", state.clip_z_min),
                                        max=("clip_z_max", state.clip_z_max),
                                        step=0.05,
                                        density="comfortable",
                                        hide_details=False,
                                        disabled=("!clip_enabled",),
                                    )

                        with vuetify.VCard(flat=True, class_="mb-3"):
                            vuetify.VCardTitle(
                                class_="d-flex align-center",
                                children=[
                                    "Probe Info",
                                    vuetify.VSpacer(),
                                    vuetify.VBtn(
                                        icon=("show_probe ? 'mdi-chevron-up' : 'mdi-chevron-down'",),
                                        variant="text",
                                        density="comfortable",
                                        click=lambda *_: setattr(state, "show_probe", not state.show_probe),
                                    ),
                                ],
                            )
                            with vuetify.VExpandTransition():
                                with vuetify.VCardText(v_show=("show_probe", state.show_probe)):
                                    vuetify.VAlert(text=("probe_label", state.probe_label), density="comfortable", variant="tonal")

                        with vuetify.VCard(flat=True):
                            vuetify.VCardTitle(
                                class_="d-flex align-center",
                                children=[
                                    "Real-Time Comparison",
                                    vuetify.VSpacer(),
                                    vuetify.VBtn(
                                        icon=("show_chart ? 'mdi-chevron-up' : 'mdi-chevron-down'",),
                                        variant="text",
                                        density="comfortable",
                                        click=lambda *_: setattr(state, "show_chart", not state.show_chart),
                                    ),
                                ],
                            )
                            with vuetify.VExpandTransition():
                                with vuetify.VCardText(v_show=("show_chart", state.show_chart)):
                                    chart_widget = Figure(
                                        style="width: 100%;",
                                        figure=build_chart(state.chart_times, state.chart_sim, state.chart_sensor),
                                    )

                with vuetify.VCol(cols=12, md=6, lg=6, class_="pa-0"):
                    view = vtk_widgets.VtkRemoteView(
                        pipeline.render_window,
                        interactive_ratio=1,
                        style="height: calc(100vh - 72px); width: 100%; background-color: #0a0c12;",
                    )
                    ctrl.view_update = view.update
                    ready = getattr(view, "on_ready", None)
                    if ready:
                        ready.add(on_reset_camera)
                    else:
                        on_reset_camera()

                    on_click = getattr(view, "on_click", None)
                    if on_click:
                        on_click.add(on_probe)
                    view.update()

                with vuetify.VCol(cols=12, md=2, lg=3, class_="pa-2", style="max-width: 360px;"):
                    with vuetify.VSheet(class_="pa-3", elevation=1, style="background-color: #0f1118; height: 100%; overflow-y: auto;"):
                        with vuetify.VCard(flat=True, class_="mb-3"):
                            vuetify.VCardTitle(
                                class_="d-flex align-center",
                                children=[
                                    "Block Manager",
                                    vuetify.VSpacer(),
                                    vuetify.VBtn(
                                        icon=("show_block_manager ? 'mdi-chevron-up' : 'mdi-chevron-down'",),
                                        variant="text",
                                        density="comfortable",
                                        click=lambda *_: setattr(state, "show_block_manager", not state.show_block_manager),
                                    ),
                                ],
                            )
                            with vuetify.VExpandTransition():
                                with vuetify.VCardText(v_show=("show_block_manager", state.show_block_manager)):
                                    vuetify.VLabel("Mostrar / ocultar bloques visibles")
                                    with vuetify.VChipGroup(
                                        v_model=("visible_blocks", state.visible_blocks),
                                        multiple=True,
                                        column=True,
                                        class_="mb-2",
                                    ):
                                        vuetify.VChip(
                                            v_for=("block in block_table",),
                                            key="block.id",
                                            value=("block.id",),
                                            label=True,
                                            color="primary",
                                            variant="tonal",
                                            class_="ma-1",
                                            size="small",
                                            children=["{{ block.name }}"],
                                        )
                                    vuetify.VSelect(
                                        label="Inspeccionar bloque",
                                        v_model=("active_block_id", state.active_block_id),
                                        items=("block_table", state.block_table),
                                        item_title="name",
                                        item_value="id",
                                        clearable=True,
                                        density="comfortable",
                                        variant="outlined",
                                        hide_details=True,
                                        class_="mb-2",
                                    )
                                    vuetify.VAlert(text=("active_block_label", state.active_block_label), density="comfortable", variant="tonal", type="info")

                        with vuetify.VCard(flat=True, class_="mb-3"):
                            vuetify.VCardTitle(
                                class_="d-flex align-center",
                                children=[
                                    "Materials",
                                    vuetify.VSpacer(),
                                    vuetify.VBtn(
                                        icon=("show_materials ? 'mdi-chevron-up' : 'mdi-chevron-down'",),
                                        variant="text",
                                        density="comfortable",
                                        click=lambda *_: setattr(state, "show_materials", not state.show_materials),
                                    ),
                                ],
                            )
                            with vuetify.VExpandTransition():
                                with vuetify.VCardText(v_show=("show_materials", state.show_materials), class_="pa-0"):
                                    vuetify.VDataTable(
                                        headers=("material_headers", state.material_headers),
                                        items=("material_table", state.material_table),
                                        dense=True,
                                        hide_default_footer=True,
                                        items_per_page=20,
                                        class_="elevation-1",
                                    )

                        with vuetify.VCard(flat=True):
                            vuetify.VCardTitle(
                                class_="d-flex align-center",
                                children=[
                                    "Blocks / Parts",
                                    vuetify.VSpacer(),
                                    vuetify.VBtn(
                                        icon=("show_blocks_table ? 'mdi-chevron-up' : 'mdi-chevron-down'",),
                                        variant="text",
                                        density="comfortable",
                                        click=lambda *_: setattr(state, "show_blocks_table", not state.show_blocks_table),
                                    ),
                                ],
                            )
                            with vuetify.VExpandTransition():
                                with vuetify.VCardText(v_show=("show_blocks_table", state.show_blocks_table), class_="pa-0"):
                                    vuetify.VDataTable(
                                        headers=("block_headers", state.block_headers),
                                        items=("block_table", state.block_table),
                                        dense=True,
                                        hide_default_footer=True,
                                        items_per_page=20,
                                        class_="elevation-1",
                                    )

if __name__ == "__main__":
    # Change port here if needed
    _start_chart_timer()
    # Bind to all interfaces so you can open from mobile on same LAN
    server.start(address="0.0.0.0", port=9012)

