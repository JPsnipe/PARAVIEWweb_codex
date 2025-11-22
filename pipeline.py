from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

import vtk

# Case-specific knobs to slightly perturb the synthetic field
CASE_VARIANTS: Dict[str, Dict] = {
    "Baseline Design": {"offset": 0.0, "noise": 25.0, "hot_spot": {"r": 1.0, "delta": 30}},
    "Eroded State 1": {"offset": -60.0, "noise": 35.0, "hot_spot": {"r": 1.15, "delta": 75}},
    "Eroded State 2": {"offset": -120.0, "noise": 45.0, "hot_spot": {"r": 1.25, "delta": 120}},
}

MATERIALS = {
    1: {"name": "Carbon Refractory", "k": 12.0, "rho": 1650, "note": "Hot face"},
    2: {"name": "High-Alumina Brick", "k": 4.2, "rho": 2300, "note": "Safety lining"},
    3: {"name": "Silica Brick", "k": 2.1, "rho": 1900, "note": "Upper stack"},
    4: {"name": "Steel Shell", "k": 45.0, "rho": 7800, "note": "Shell"},
}


class FurnacePipeline:
    """
    Build and manage the VTK pipeline for the furnace mockup.

    The synthetic geometry uses an implicit cylinder-with-hole sampled onto a
    vtkImageData grid. That grid is given an analytic temperature distribution
    that mimics a hot core and cooler shell. The structure here mirrors what a
    real .rst/.cdb/.vtu reader would return, so swapping the generator for an
    Ansys reader later only needs to replace _generate_volume().
    """

    def __init__(self):
        self.case_name = "Baseline Design"
        self.outer_radius = 1.8
        self.inner_radius = 0.7
        self.height = 6.0
        self.color_range = (50.0, 1650.0)

        self.block_definitions = self._build_block_definitions()
        self.visible_block_ids = [block["id"] for block in self.block_definitions]

        self.renderer = vtk.vtkRenderer()
        self.render_window = vtk.vtkRenderWindow()
        self.render_window.AddRenderer(self.renderer)
        # Attach an interactor so remote helpers can drive the render window
        self.interactor = vtk.vtkRenderWindowInteractor()
        self.interactor.SetRenderWindow(self.render_window)
        self.render_window.SetOffScreenRendering(1)

        self.picker = vtk.vtkCellPicker()
        self.picker.SetTolerance(0.002)

        self.lut = self._build_inferno_lut()
        self.scalar_bar = self._build_scalar_bar()

        self.clip_plane = vtk.vtkPlane()
        self.clip_enabled = False

        self.distance_data = None
        self.temperature_data = None
        self.shell_surface = None
        self.shell_probe = None
        self.shell_clip = None
        self.shell_append = None
        self.shell_thresholds: Dict[int, vtk.vtkThreshold] = {}
        self.shell_mapper = None
        self.shell_actor = None
        self.isotherm = None
        self.iso_probe = None
        self.iso_clip = None
        self.iso_append = None
        self.iso_thresholds: Dict[int, vtk.vtkThreshold] = {}
        self.iso_mapper = None
        self.iso_actor = None
        self.probe_locator = None

        self.bounds: Tuple[float, ...] = (0,) * 6
        self.material_table = []
        self.block_table = []

        self._build_pipeline()

    # --------------------------------------------------------------------- #
    # Pipeline creation
    # --------------------------------------------------------------------- #
    def _build_pipeline(self):
        self.distance_data, self.temperature_data = self._generate_volume(self.case_name)
        self.bounds = self.temperature_data.GetBounds()
        self._update_tables()

        self._setup_shell_actor()
        self._setup_iso_actor(iso_value=800.0)

        self.renderer.SetBackground(0.08, 0.08, 0.1)
        self.renderer.AddActor2D(self.scalar_bar)
        self.renderer.ResetCamera()
        self.interactor.Initialize()
        self.render_window.Render()

    def _setup_shell_actor(self):
        # Extract the double surface (outer + inner) of the implicit shell
        self.shell_surface = vtk.vtkFlyingEdges3D()
        self.shell_surface.SetInputData(self.distance_data)
        self.shell_surface.ComputeNormalsOn()
        self.shell_surface.SetValue(0, 0.0)

        # Sample temperature onto that geometry
        self.shell_probe = vtk.vtkProbeFilter()
        self.shell_probe.SetInputConnection(self.shell_surface.GetOutputPort())
        self.shell_probe.SetSourceData(self.temperature_data)

        self.shell_thresholds = self._create_block_thresholds(self.shell_probe)
        self.shell_append = vtk.vtkAppendFilter()
        for bid in self.visible_block_ids:
            self.shell_append.AddInputConnection(self.shell_thresholds[bid].GetOutputPort())

        # Optional clip plane
        self.shell_clip = vtk.vtkClipDataSet()
        self.shell_clip.SetInputConnection(self.shell_append.GetOutputPort())
        self.shell_clip.SetClipFunction(self.clip_plane)
        self.shell_clip.InsideOutOn()

        self.shell_mapper = vtk.vtkDataSetMapper()
        self.shell_mapper.SetLookupTable(self.lut)
        self.shell_mapper.UseLookupTableScalarRangeOn()
        self.shell_mapper.SetScalarModeToUsePointFieldData()
        self.shell_mapper.SelectColorArray("Temperature")
        self.shell_mapper.SetInputConnection(self.shell_append.GetOutputPort())

        self.shell_actor = vtk.vtkActor()
        self.shell_actor.SetMapper(self.shell_mapper)
        self.shell_actor.GetProperty().SetOpacity(0.9)
        self.shell_actor.GetProperty().SetEdgeVisibility(False)

        self.renderer.AddActor(self.shell_actor)
        self._update_probe_locator()

    def _setup_iso_actor(self, iso_value: float):
        self.isotherm = vtk.vtkFlyingEdges3D()
        self.isotherm.SetInputData(self.temperature_data)
        self.isotherm.ComputeNormalsOn()
        self.isotherm.SetValue(0, iso_value)

        self.iso_probe = vtk.vtkProbeFilter()
        self.iso_probe.SetInputConnection(self.isotherm.GetOutputPort())
        self.iso_probe.SetSourceData(self.temperature_data)

        self.iso_thresholds = self._create_block_thresholds(self.iso_probe)
        self.iso_append = vtk.vtkAppendFilter()
        for bid in self.visible_block_ids:
            self.iso_append.AddInputConnection(self.iso_thresholds[bid].GetOutputPort())

        self.iso_clip = vtk.vtkClipDataSet()
        self.iso_clip.SetInputConnection(self.iso_append.GetOutputPort())
        self.iso_clip.SetClipFunction(self.clip_plane)
        self.iso_clip.InsideOutOn()

        self.iso_mapper = vtk.vtkDataSetMapper()
        self.iso_mapper.SetLookupTable(self.lut)
        self.iso_mapper.UseLookupTableScalarRangeOn()
        self.iso_mapper.SetScalarModeToUsePointFieldData()
        self.iso_mapper.SelectColorArray("Temperature")
        self.iso_mapper.SetInputConnection(self.iso_append.GetOutputPort())

        self.iso_actor = vtk.vtkActor()
        self.iso_actor.SetMapper(self.iso_mapper)
        self.iso_actor.GetProperty().SetOpacity(0.45)
        self.iso_actor.GetProperty().SetEdgeVisibility(False)

        self.renderer.AddActor(self.iso_actor)

    def _build_inferno_lut(self) -> vtk.vtkLookupTable:
        # Approximate Inferno colormap without extra dependencies
        ctf = vtk.vtkColorTransferFunction()
        ctf.AddRGBPoint(0.0, 0.0, 0.0, 0.0)
        ctf.AddRGBPoint(0.25, 0.22, 0.02, 0.40)
        ctf.AddRGBPoint(0.50, 0.68, 0.16, 0.16)
        ctf.AddRGBPoint(0.75, 0.98, 0.64, 0.05)
        ctf.AddRGBPoint(1.0, 0.99, 0.98, 0.65)

        lut = vtk.vtkLookupTable()
        lut.SetNumberOfTableValues(256)
        lut.SetRange(*self.color_range)
        for i in range(256):
            r, g, b = ctf.GetColor(i / 255.0)
            lut.SetTableValue(i, r, g, b, 1.0)
        lut.Build()
        return lut

    def _build_scalar_bar(self) -> vtk.vtkScalarBarActor:
        scalar_bar = vtk.vtkScalarBarActor()
        scalar_bar.SetLookupTable(self.lut)
        scalar_bar.SetNumberOfLabels(5)
        scalar_bar.SetTitle("Temperature (deg C)")
        scalar_bar.VisibilityOn()
        return scalar_bar

    def _create_block_thresholds(self, source_alg) -> Dict[int, vtk.vtkThreshold]:
        thresholds: Dict[int, vtk.vtkThreshold] = {}
        for entry in self.block_definitions:
            bid = entry["id"]
            th = vtk.vtkThreshold()
            th.SetInputConnection(source_alg.GetOutputPort())
            th.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, "BlockId")
            low, high = bid - 0.49, bid + 0.49
            if hasattr(th, "ThresholdBetween"):
                th.ThresholdBetween(low, high)
            else:
                th.SetLowerThreshold(low)
                th.SetUpperThreshold(high)
                if hasattr(vtk.vtkThreshold, "THRESHOLD_BETWEEN"):
                    th.SetThresholdFunction(vtk.vtkThreshold.THRESHOLD_BETWEEN)
            th.SetUseContinuousCellRange(False)
            thresholds[bid] = th
        return thresholds

    # --------------------------------------------------------------------- #
    # Data generation
    # --------------------------------------------------------------------- #
    def _generate_volume(self, case_name: str):
        """
        Create the synthetic hollow cylinder and populate it with temperature.

        To replace with Ansys reader: swap this function for a wrapper around
        vtkANSYSReader / vtkEnSightGoldReader or a custom .rst parser that
        returns a vtkDataSet with the same Temperature point-data array.
        """
        params = CASE_VARIANTS.get(case_name, CASE_VARIANTS["Baseline Design"])

        implicit_shell = self._create_shell_implicit()

        sampler = vtk.vtkSampleFunction()
        sampler.SetImplicitFunction(implicit_shell)
        sampler.SetModelBounds(
            -self.outer_radius,
            self.outer_radius,
            -self.outer_radius,
            self.outer_radius,
            -self.height * 0.5,
            self.height * 0.5,
        )
        sampler.SetSampleDimensions(80, 80, 120)
        sampler.ComputeNormalsOff()
        sampler.Update()

        distance_data = vtk.vtkImageData()
        distance_data.DeepCopy(sampler.GetOutput())

        temperature_data = vtk.vtkImageData()
        temperature_data.DeepCopy(sampler.GetOutput())

        temperatures = vtk.vtkFloatArray()
        temperatures.SetName("Temperature")
        temperatures.SetNumberOfComponents(1)
        temperatures.SetNumberOfTuples(temperature_data.GetNumberOfPoints())

        material_ids = vtk.vtkIntArray()
        material_ids.SetName("MaterialId")
        material_ids.SetNumberOfComponents(1)
        material_ids.SetNumberOfTuples(temperature_data.GetNumberOfPoints())

        block_ids = vtk.vtkIntArray()
        block_ids.SetName("BlockId")
        block_ids.SetNumberOfComponents(1)
        block_ids.SetNumberOfTuples(temperature_data.GetNumberOfPoints())

        for pid in range(temperature_data.GetNumberOfPoints()):
            x, y, z = temperature_data.GetPoint(pid)
            temp, mat_id = self._temperature_profile(x, y, z, params)
            r = math.sqrt(x * x + y * y)
            radial_span = max(self.outer_radius - self.inner_radius, 1e-3)
            radial_frac = min(1.0, max(0.0, (r - self.inner_radius) / radial_span))
            vertical_frac = min(1.0, max(0.0, (z + self.height * 0.5) / self.height))
            block_id = self._block_id_from_position(radial_frac, vertical_frac)
            temperatures.SetValue(pid, temp)
            material_ids.SetValue(pid, mat_id)
            block_ids.SetValue(pid, block_id)

        temperature_data.GetPointData().SetScalars(temperatures)
        temperature_data.GetPointData().SetActiveScalars("Temperature")
        temperature_data.GetPointData().AddArray(material_ids)
        temperature_data.GetPointData().AddArray(block_ids)

        return distance_data, temperature_data

    def _create_shell_implicit(self) -> vtk.vtkImplicitFunction:
        outer = vtk.vtkCylinder()
        outer.SetRadius(self.outer_radius)

        inner = vtk.vtkCylinder()
        inner.SetRadius(self.inner_radius)

        shell = vtk.vtkImplicitBoolean()
        shell.SetOperationTypeToDifference()
        shell.AddFunction(outer)
        shell.AddFunction(inner)

        limiter = vtk.vtkBox()
        limiter.SetBounds(
            -self.outer_radius,
            self.outer_radius,
            -self.outer_radius,
            self.outer_radius,
            -self.height * 0.5,
            self.height * 0.5,
        )

        bounded = vtk.vtkImplicitBoolean()
        bounded.SetOperationTypeToIntersection()
        bounded.AddFunction(shell)
        bounded.AddFunction(limiter)

        return bounded

    def _build_block_definitions(self) -> List[Dict]:
        bands = ["Bottom", "Mid", "Top"]
        layers = ["Hot Face", "Safety", "Shell"]
        definitions = []
        for band in bands:
            for layer in layers:
                definitions.append({"id": len(definitions) + 1, "band": band, "layer": layer, "name": f"{band} - {layer}"})
        return definitions

    def _block_id_from_position(self, radial_frac: float, vertical_frac: float) -> int:
        layer = "Hot Face" if radial_frac < 0.33 else "Safety" if radial_frac < 0.66 else "Shell"
        band = "Bottom" if vertical_frac < 0.33 else "Mid" if vertical_frac < 0.66 else "Top"
        for entry in self.block_definitions:
            if entry["band"] == band and entry["layer"] == layer:
                return entry["id"]
        return 0

    def _temperature_profile(self, x: float, y: float, z: float, params: Dict) -> Tuple[float, int]:
        r = math.sqrt(x * x + y * y)
        radial_span = max(self.outer_radius - self.inner_radius, 1e-3)
        radial_frac = min(1.0, max(0.0, (r - self.inner_radius) / radial_span))
        vertical_frac = min(1.0, max(0.0, (z + self.height * 0.5) / self.height))

        base = 1600.0 - radial_frac * 1550.0 - vertical_frac * 80.0 + params.get("offset", 0.0)
        noise_amp = params.get("noise", 25.0)
        noise = random.uniform(-noise_amp, noise_amp)

        hot_spot = params.get("hot_spot", {"r": 1.0, "delta": 0.0})
        hot_term = math.exp(-((r - hot_spot.get("r", 1.0)) ** 2) / 0.15) * hot_spot.get("delta", 0.0)

        temperature = base + noise + hot_term
        material_id = self._material_id(radial_frac, vertical_frac)
        return min(self.color_range[1], max(self.color_range[0], temperature)), material_id

    def _material_id(self, radial_frac: float, vertical_frac: float) -> int:
        if radial_frac < 0.33:
            return 1  # Carbon refractory
        if radial_frac < 0.66:
            return 2 if vertical_frac < 0.65 else 3  # Safety lining / silica upper
        return 4  # Steel shell

    def set_block_visibility(self, block_ids):
        requested = set()
        for bid in block_ids or []:
            try:
                requested.add(int(bid))
            except (TypeError, ValueError):
                continue

        valid_ids = {entry["id"] for entry in self.block_definitions}
        clean = [bid for bid in requested if bid in valid_ids]
        if not clean:
            clean = list(valid_ids)

        self.visible_block_ids = sorted(clean)
        self._rebuild_visibility_inputs()

    def _rebuild_visibility_inputs(self):
        if not self.shell_append or not self.iso_append:
            return

        def rebuild(append_filter, thresholds: Dict[int, vtk.vtkThreshold]):
            append_filter.RemoveAllInputs()
            for bid in self.visible_block_ids:
                th = thresholds.get(bid)
                if th:
                    append_filter.AddInputConnection(th.GetOutputPort())
            append_filter.Modified()

        rebuild(self.shell_append, self.shell_thresholds)
        rebuild(self.iso_append, self.iso_thresholds)
        self._update_probe_locator()
        self.render_window.Render()

    # --------------------------------------------------------------------- #
    # Updates
    # --------------------------------------------------------------------- #
    def update_case(self, case_name: str):
        self.case_name = case_name
        self.distance_data, self.temperature_data = self._generate_volume(case_name)
        self.bounds = self.temperature_data.GetBounds()
        self._update_tables()

        self.shell_surface.SetInputData(self.distance_data)
        self.shell_surface.Modified()
        self.shell_probe.SetSourceData(self.temperature_data)
        self.shell_probe.Modified()

        self.isotherm.SetInputData(self.temperature_data)
        self.isotherm.Modified()
        if self.iso_probe:
            self.iso_probe.SetSourceData(self.temperature_data)
            self.iso_probe.Modified()

        self._rebuild_visibility_inputs()

    def update_iso_value(self, iso_value: float):
        self.isotherm.SetValue(0, float(iso_value))
        self.isotherm.Modified()

    def update_opacity(self, opacity: float):
        self.shell_actor.GetProperty().SetOpacity(float(opacity))

    def update_clip(self, enabled: bool, axis: str, x: float, y: float, z: float):
        axis = axis.upper()
        normals = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
        normal = normals.get(axis, (0.0, 0.0, 1.0))
        self.clip_plane.SetOrigin(float(x), float(y), float(z))
        self.clip_plane.SetNormal(*normal)
        self.clip_plane.Modified()

        self.clip_enabled = enabled
        self._use_clip_outputs(enabled)
        self._update_probe_locator()

    def reset_camera(self):
        self.renderer.ResetCamera()

    def _use_clip_outputs(self, enabled: bool):
        if enabled:
            self.shell_mapper.SetInputConnection(self.shell_clip.GetOutputPort())
            self.iso_mapper.SetInputConnection(self.iso_clip.GetOutputPort())
        else:
            self.shell_mapper.SetInputConnection(self.shell_append.GetOutputPort())
            self.iso_mapper.SetInputConnection(self.iso_append.GetOutputPort())

    def _update_probe_locator(self):
        target = self.shell_clip if self.clip_enabled and self.shell_clip else self.shell_append or self.shell_probe
        if target is None:
            return
        target.Update()
        self.probe_locator = vtk.vtkPointLocator()
        self.probe_locator.SetDataSet(target.GetOutput())
        self.probe_locator.BuildLocator()

    # --------------------------------------------------------------------- #
    # Interaction
    # --------------------------------------------------------------------- #
    def pick(self, x: float, y: float):
        if x is None or y is None:
            return None

        picked = self.picker.Pick(float(x), float(y), 0, self.renderer)
        if not picked:
            return None

        pos = self.picker.GetPickPosition()
        if self.probe_locator is None:
            return None

        pid = self.probe_locator.FindClosestPoint(pos)
        target = self.shell_clip if self.clip_enabled and self.shell_clip else self.shell_append or self.shell_probe
        data = target.GetOutput()
        temperature_array = data.GetPointData().GetArray("Temperature")
        material_array = data.GetPointData().GetArray("MaterialId")
        block_array = data.GetPointData().GetArray("BlockId")

        if pid < 0 or temperature_array is None:
            return None

        value = float(temperature_array.GetTuple1(pid))
        return {
            "point_id": int(pid),
            "temperature": round(value, 1),
            "position": tuple(round(v, 3) for v in pos),
            "material_id": int(material_array.GetTuple1(pid)) if material_array else None,
            "block_id": int(block_array.GetTuple1(pid)) if block_array else None,
        }

    # ------------------------------------------------------------------ #
    # Metadata tables
    # ------------------------------------------------------------------ #
    def _update_tables(self):
        # Materials table from constants
        self.material_table = []
        for mid, data in MATERIALS.items():
            entry = {"id": mid, "name": data["name"], "k": data["k"], "rho": data["rho"], "note": data["note"]}
            self.material_table.append(entry)

        # Blocks table: coarse zones by height + radial layer
        accum = {}
        temps = self.temperature_data.GetPointData().GetArray("Temperature")
        mats = self.temperature_data.GetPointData().GetArray("MaterialId")
        blocks = self.temperature_data.GetPointData().GetArray("BlockId")
        npts = self.temperature_data.GetNumberOfPoints()
        for pid in range(npts):
            bid = int(blocks.GetTuple1(pid)) if blocks else -1
            mid = int(mats.GetTuple1(pid)) if mats else -1
            temp = float(temps.GetTuple1(pid))
            if bid not in accum:
                meta = next((b for b in self.block_definitions if b["id"] == bid), {"name": f"Block {bid}", "band": "N/A", "layer": "N/A"})
                accum[bid] = {
                    "count": 0,
                    "sum": 0.0,
                    "min": 1e9,
                    "max": -1e9,
                    "material_id": mid,
                    "band": meta["band"],
                    "layer": meta["layer"],
                    "name": meta["name"],
                }
            acc = accum[bid]
            acc["count"] += 1
            acc["sum"] += temp
            acc["min"] = min(acc["min"], temp)
            acc["max"] = max(acc["max"], temp)

        self.block_table = []
        for bid in sorted(accum.keys()):
            acc = accum[bid]
            avg = acc["sum"] / acc["count"]
            self.block_table.append(
                {
                    "id": bid,
                    "name": acc["name"],
                    "material_id": acc["material_id"],
                    "material": MATERIALS.get(acc["material_id"], {}).get("name", "N/A"),
                    "t_min": round(acc["min"], 1),
                    "t_max": round(acc["max"], 1),
                    "t_avg": round(avg, 1),
                    "band": acc["band"],
                    "layer": acc["layer"],
                }
            )

    # ------------------------------------------------------------------ #
    # Camera helpers
    # ------------------------------------------------------------------ #
    def camera_orbit(self, azimuth: float = 0.0, elevation: float = 0.0):
        cam = self.renderer.GetActiveCamera()
        if azimuth:
            cam.Azimuth(azimuth)
        if elevation:
            cam.Elevation(elevation)
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()

    def camera_zoom(self, factor: float = 1.2):
        cam = self.renderer.GetActiveCamera()
        cam.Dolly(factor)
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()

    def camera_pan(self, dx: float = 0.0, dy: float = 0.0):
        cam = self.renderer.GetActiveCamera()
        fp = list(cam.GetFocalPoint())
        pos = list(cam.GetPosition())
        view_up = cam.GetViewUp()
        normal = cam.GetViewPlaneNormal()
        # Right vector = normal x up
        right = [
            normal[1] * view_up[2] - normal[2] * view_up[1],
            normal[2] * view_up[0] - normal[0] * view_up[2],
            normal[0] * view_up[1] - normal[1] * view_up[0],
        ]
        scale = 0.1 * self.outer_radius
        for i in range(3):
            shift = (-dx * right[i] + dy * view_up[i]) * scale
            fp[i] += shift
            pos[i] += shift
        cam.SetFocalPoint(*fp)
        cam.SetPosition(*pos)
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()
