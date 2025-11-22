import math
import random
import threading

import plotly.graph_objects as go
from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vtk as vtk_widgets, vuetify3 as vuetify
from trame.widgets.plotly import Figure

from pipeline import CASE_VARIANTS, FurnacePipeline

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
    ctrl.view_update()


def on_reset_camera():
    pipeline.reset_camera()
    ctrl.view_update()


def on_probe(**kwargs):
    x = kwargs.get("x") or kwargs.get("position", [None, None])[0]
    y = kwargs.get("y") or kwargs.get("position", [None, None])[1]
    info = pipeline.pick(x, y)
    if info:
        state.probe_label = (
            f"Node {info['point_id']}: {info['temperature']} deg C (mat {info.get('material_id')}) at {info['position']}"
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
        vuetify.VBtn(
            "Reset Camera",
            icon="mdi-crosshairs-gps",
            click=on_reset_camera,
            outlined=True,
            dense=True,
        )
        vuetify.VBtn(icon="mdi-undo-variant", dense=True, title="Orbit Left", click=lambda *_: on_orbit("left"))
        vuetify.VBtn(icon="mdi-redo-variant", dense=True, title="Orbit Right", click=lambda *_: on_orbit("right"))
        vuetify.VBtn(icon="mdi-arrow-up-bold", dense=True, title="Orbit Up", click=lambda *_: on_orbit("up"))
        vuetify.VBtn(icon="mdi-arrow-down-bold", dense=True, title="Orbit Down", click=lambda *_: on_orbit("down"))
        vuetify.VBtn(icon="mdi-magnify-plus", dense=True, title="Zoom In", click=lambda *_: on_zoom(1.2))
        vuetify.VBtn(icon="mdi-magnify-minus", dense=True, title="Zoom Out", click=lambda *_: on_zoom(0.8))
        vuetify.VBtn(icon="mdi-cursor-move", dense=True, title="Pan Up", click=lambda *_: on_pan(0, 1))
        vuetify.VBtn(icon="mdi-cursor-move", dense=True, title="Pan Down", class_="rotate-180", click=lambda *_: on_pan(0, -1))
        vuetify.VSpacer()

    with layout.content:
        with vuetify.VContainer(fluid=True, class_="fill-height pa-0"):
            with vuetify.VRow(no_gutters=True, class_="fill-height"):
                with vuetify.VCol(cols=12, md=4, lg=3, class_="pa-2", style="max-width: 360px;"):
                    with vuetify.VSheet(class_="pa-3", elevation=1, style="background-color: #0f1118;"):
                        with vuetify.VCard(flat=True, class_="mb-4"):
                            vuetify.VCardTitle("Simulation Case")
                            vuetify.VSelect(
                                v_model=("case_name", state.case_name),
                                items=("case_items", state.case_items),
                                dense=True,
                                hide_details=True,
                                outlined=True,
                            )

                        with vuetify.VCard(flat=True, class_="mb-4"):
                            vuetify.VCardTitle("Visualization")
                            vuetify.VCardText(
                                children=[
                                    vuetify.VSlider(
                                        label="Isotherm (deg C)",
                                        v_model=("temperature_iso", state.temperature_iso),
                                        min=pipeline.color_range[0],
                                        max=pipeline.color_range[1],
                                        step=10,
                                        dense=True,
                                        hide_details=False,
                                    ),
                                    vuetify.VSlider(
                                        label="Shell Opacity",
                                        v_model=("shell_opacity", state.shell_opacity),
                                        min=0.1,
                                        max=1.0,
                                        step=0.05,
                                        dense=True,
                                        hide_details=False,
                                    ),
                                ]
                            )

                        with vuetify.VCard(flat=True, class_="mb-4"):
                            vuetify.VCardTitle("Cut Plane")
                            vuetify.VCardText(
                                children=[
                                    vuetify.VSwitch(
                                        label="Enable",
                                        inset=True,
                                        v_model=("clip_enabled", state.clip_enabled),
                                    ),
                                    vuetify.VSelect(
                                        label="Axis",
                                        items=["X", "Y", "Z"],
                                        v_model=("clip_axis", state.clip_axis),
                                        dense=True,
                                        hide_details=True,
                                        outlined=True,
                                        disabled=("!clip_enabled",),
                                    ),
                                    vuetify.VSlider(
                                        label="X Offset",
                                        v_model=("clip_x", state.clip_x),
                                        min=("clip_x_min", state.clip_x_min),
                                        max=("clip_x_max", state.clip_x_max),
                                        step=0.05,
                                        dense=True,
                                        hide_details=False,
                                        disabled=("!clip_enabled",),
                                    ),
                                    vuetify.VSlider(
                                        label="Y Offset",
                                        v_model=("clip_y", state.clip_y),
                                        min=("clip_y_min", state.clip_y_min),
                                        max=("clip_y_max", state.clip_y_max),
                                        step=0.05,
                                        dense=True,
                                        hide_details=False,
                                        disabled=("!clip_enabled",),
                                    ),
                                    vuetify.VSlider(
                                        label="Z Offset",
                                        v_model=("clip_z", state.clip_z),
                                        min=("clip_z_min", state.clip_z_min),
                                        max=("clip_z_max", state.clip_z_max),
                                        step=0.05,
                                        dense=True,
                                        hide_details=False,
                                        disabled=("!clip_enabled",),
                                    ),
                                ]
                            )

                        with vuetify.VCard(flat=True, class_="mb-4"):
                            vuetify.VCardTitle("Probe Info")
                            vuetify.VCardText(
                                children=[vuetify.VAlert(text=("probe_label", state.probe_label), dense=True, outlined=True)]
                            )

                        with vuetify.VCard(flat=True):
                            vuetify.VCardTitle("Real-Time Comparison")
                            with vuetify.VCardText():
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
                        with vuetify.VCard(flat=True, class_="mb-4"):
                            vuetify.VCardTitle("Materials")
                            vuetify.VDataTable(
                                headers=[
                                    {"text": "ID", "value": "id", "width": 50},
                                    {"text": "Name", "value": "name"},
                                    {"text": "k (W/mK)", "value": "k", "width": 90},
                                    {"text": "ρ (kg/m3)", "value": "rho", "width": 90},
                                ],
                                items=("material_table", state.material_table),
                                dense=True,
                                hide_default_footer=True,
                                items_per_page=20,
                                class_="elevation-1",
                            )

                        with vuetify.VCard(flat=True):
                            vuetify.VCardTitle("Blocks / Parts")
                            vuetify.VDataTable(
                                headers=[
                                    {"text": "#", "value": "id", "width": 40},
                                    {"text": "Zone", "value": "name"},
                                    {"text": "Mat", "value": "material", "width": 110},
                                    {"text": "Tavg", "value": "t_avg", "width": 70},
                                    {"text": "Tmin", "value": "t_min", "width": 70},
                                    {"text": "Tmax", "value": "t_max", "width": 70},
                                ],
                                items=("block_table", state.block_table),
                                dense=True,
                                hide_default_footer=True,
                                items_per_page=20,
                                class_="elevation-1",
                            )

if __name__ == "__main__":
    # Change port here if needed
    _start_chart_timer()
    server.start(port=9010)
