from __future__ import annotations

import math
import random
from typing import Dict, Tuple

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
        self.shell_mapper = None
        self.shell_actor = None
        self.isotherm = None
        self.iso_clip = None
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

        # Optional clip plane
        self.shell_clip = vtk.vtkClipPolyData()
        self.shell_clip.SetInputConnection(self.shell_probe.GetOutputPort())
        self.shell_clip.SetClipFunction(self.clip_plane)
        self.shell_clip.InsideOutOn()

        self.shell_mapper = vtk.vtkPolyDataMapper()
        self.shell_mapper.SetLookupTable(self.lut)
        self.shell_mapper.UseLookupTableScalarRangeOn()
        self.shell_mapper.SetScalarModeToUsePointFieldData()
        self.shell_mapper.SelectColorArray("Temperature")
        self.shell_mapper.SetInputConnection(self.shell_probe.GetOutputPort())

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

        self.iso_clip = vtk.vtkClipPolyData()
        self.iso_clip.SetInputConnection(self.isotherm.GetOutputPort())
        self.iso_clip.SetClipFunction(self.clip_plane)
        self.iso_clip.InsideOutOn()

        self.iso_mapper = vtk.vtkPolyDataMapper()
        self.iso_mapper.SetLookupTable(self.lut)
        self.iso_mapper.UseLookupTableScalarRangeOn()
        self.iso_mapper.SetScalarModeToUsePointFieldData()
        self.iso_mapper.SelectColorArray("Temperature")
        self.iso_mapper.SetInputConnection(self.isotherm.GetOutputPort())

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

        for pid in range(temperature_data.GetNumberOfPoints()):
            x, y, z = temperature_data.GetPoint(pid)
            temp, mat_id = self._temperature_profile(x, y, z, params)
            temperatures.SetValue(pid, temp)
            material_ids.SetValue(pid, mat_id)

        temperature_data.GetPointData().SetScalars(temperatures)
        temperature_data.GetPointData().SetActiveScalars("Temperature")
        temperature_data.GetPointData().AddArray(material_ids)

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

        self._update_probe_locator()

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

    def reset_camera(self):
        self.renderer.ResetCamera()

    def _use_clip_outputs(self, enabled: bool):
        if enabled:
            self.shell_mapper.SetInputConnection(self.shell_clip.GetOutputPort())
            self.iso_mapper.SetInputConnection(self.iso_clip.GetOutputPort())
        else:
            self.shell_mapper.SetInputConnection(self.shell_probe.GetOutputPort())
            self.iso_mapper.SetInputConnection(self.isotherm.GetOutputPort())

    def _update_probe_locator(self):
        self.probe_locator = vtk.vtkPointLocator()
        self.probe_locator.SetDataSet(self.shell_probe.GetOutput())
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
        data = self.shell_probe.GetOutput()
        temperature_array = data.GetPointData().GetArray("Temperature")
        material_array = data.GetPointData().GetArray("MaterialId")

        if pid < 0 or temperature_array is None:
            return None

        value = float(temperature_array.GetTuple1(pid))
        return {
            "point_id": int(pid),
            "temperature": round(value, 1),
            "position": tuple(round(v, 3) for v in pos),
            "material_id": int(material_array.GetTuple1(pid)) if material_array else None,
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
        npts = self.temperature_data.GetNumberOfPoints()
        temp_sum = 0.0
        temp_min = float("inf")
        temp_max = float("-inf")
        for pid in range(npts):
            x, y, z = self.temperature_data.GetPoint(pid)
            r = math.sqrt(x * x + y * y)
            radial_span = max(self.outer_radius - self.inner_radius, 1e-3)
            radial_frac = min(1.0, max(0.0, (r - self.inner_radius) / radial_span))
            vertical_frac = min(1.0, max(0.0, (z + self.height * 0.5) / self.height))

            layer = "Hot Face" if radial_frac < 0.33 else "Safety" if radial_frac < 0.66 else "Shell"
            band = "Bottom" if vertical_frac < 0.33 else "Mid" if vertical_frac < 0.66 else "Top"
            key = f"{band} - {layer}"
            mid = int(mats.GetTuple1(pid)) if mats else -1
            temp = float(temps.GetTuple1(pid))
            temp_sum += temp
            temp_min = min(temp_min, temp)
            temp_max = max(temp_max, temp)
            if key not in accum:
                accum[key] = {"count": 0, "sum": 0.0, "min": 1e9, "max": -1e9, "material_id": mid, "band": band, "layer": layer}
            acc = accum[key]
            acc["count"] += 1
            acc["sum"] += temp
            acc["min"] = min(acc["min"], temp)
            acc["max"] = max(acc["max"], temp)

        self.block_table = []
        for idx, (key, acc) in enumerate(sorted(accum.items())):
            avg = acc["sum"] / acc["count"]
            self.block_table.append(
                {
                    "id": idx + 1,
                    "name": key,
                    "material_id": acc["material_id"],
                    "material": MATERIALS.get(acc["material_id"], {}).get("name", "N/A"),
                    "t_min": round(acc["min"], 1),
                    "t_max": round(acc["max"], 1),
                    "t_avg": round(avg, 1),
                    "band": acc["band"],
                    "layer": acc["layer"],
                }
            )

        hot_block = max(self.block_table, key=lambda entry: entry["t_max"], default=None)
        avg_temperature = temp_sum / npts if npts else 0.0
        self.metrics = {
            "min": round(temp_min if npts else 0.0, 1),
            "max": round(temp_max if npts else 0.0, 1),
            "avg": round(avg_temperature, 1),
            "hot_block": hot_block["name"] if hot_block else "N/A",
            "hot_material": hot_block["material"] if hot_block else "N/A",
            "hot_tmax": hot_block["t_max"] if hot_block else 0.0,
        }

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
        right = [0, 0, 0]
        cam.GetViewPlaneNormal()  # ensure internal consistency
        # Simple screen-space pan approximation
        cam.OrthogonalizeViewUp()
        cam.GetViewRight(right)
        scale = 0.1 * self.outer_radius
        for i in range(3):
            shift = (-dx * right[i] + dy * view_up[i]) * scale
            fp[i] += shift
            pos[i] += shift
        cam.SetFocalPoint(*fp)
        cam.SetPosition(*pos)
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()

    def camera_view(self, preset: str):
        cam = self.renderer.GetActiveCamera()
        distance = self.outer_radius * 2.6
        height_offset = self.height * 0.55
        presets = {
            "front": ((distance, 0.0, height_offset), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            "side": ((0.0, -distance, height_offset * 0.5), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            "top": ((0.0, 0.0, distance * 0.8), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        }

        if preset in presets:
            pos, focal, view_up = presets[preset]
            cam.SetPosition(*pos)
            cam.SetFocalPoint(*focal)
            cam.SetViewUp(*view_up)
            self.renderer.ResetCameraClippingRange()
            self.render_window.Render()
