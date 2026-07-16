import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional
from PIL import Image, ImageTk


LAYOUTS = [
    "Rectangular building",
    "L-shaped building",
    "T-shaped building",
    "U-shaped building",
    "Hollow building",
]

LAYOUT_IMAGES = {
    "Rectangular building": os.path.join("input_files", "layout_images", "rectangular_building.png"),
    "L-shaped building":    os.path.join("input_files", "layout_images", "l_shaped_building.png"),
    "T-shaped building":    os.path.join("input_files", "layout_images", "t_shaped_building.png"),
    "U-shaped building":    os.path.join("input_files", "layout_images", "u_shaped_building.png"),
    "Hollow building":      os.path.join("input_files", "layout_images", "hollow_building.png"),
}

FENESTRATION_TYPES = [
    ("WWR 0.3", os.path.join("input_files", "WWR_30.png")),
    ("WWR 0.5", os.path.join("input_files", "WWR_50.png")),
    ("WWR 0.7", os.path.join("input_files", "WWR_70.png")),
]

SECONDARY_DIMS_REQUIRED = {
    "Rectangular building": False,
    "L-shaped building": True,
    "T-shaped building": True,
    "U-shaped building": True,
    "Hollow building": True,
}

_DEFAULT_EPW = os.path.join("input_files", "CAN_ON_Ottawa.716280_CWEC.epw")

defaults = {
    "layout": "Rectangular building",
    "a": 30.0, "b": 30.0, "c": None, "d": None,
    "ceiling_height": 3.0,
    "above_gnd_floors": 1,
    "basement_floors": 0,
    "WWR": 0.5,
    "fenestration_description": "",
    "details": "Add more details on the building, such as: building use,zoning, envelope details, fenestration, etc.",
    "location": "Ottawa",
    "age": "2021, between 1995 and 1999, 1980s",
    "orientation": "S",
    # Gains
    "people_description": "Each floor has 25 people ...\nThe occupancy density is 20 m2/person ...",
    "lighting_description": "The building is equiped with LED lights ...\nThe lighting density is 6 W/m2 ...",
    "equipment_description": "Each zone has a PC, a monitor and a printer ...",
    "hvac_description": "The building has an AHU VAV system, with economizer and heat recovery. Each zone has an electric baseboard heater.",
    # HVAC setpoints
    "occ_heat_sp": 21.0,
    "occ_cool_sp": 24.0,
    "unocc_heat_sp": 16.0,
    "unocc_cool_sp": 28.0,
    # Schedules (HH:MM)
    "hvac_start_wd": "06:00", "hvac_end_wd": "22:00",
    "hvac_start_sat": "08:00", "hvac_end_sat": "18:00",
    "hvac_start_sun": "08:00", "hvac_end_sun": "18:00",
    "occ_start_wd": "08:00", "occ_end_wd": "18:00",
    "occ_start_sat": "09:00", "occ_end_sat": "17:00",
    "occ_start_sun": "09:00", "occ_end_sun": "17:00",
    "zones_per_floor": "1 zone",
}


class BuildingInputGUI:
    def __init__(self, root: tk.Tk, on_submit=None):
        self.root = root
        self.on_submit = on_submit
        self.result: Optional[dict] = None

        root.title("GHGe Modeller")
        root.resizable(True, True)

        outer = ttk.Frame(root, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        # ── Notebook ──────────────────────────────────────────────────────────
        notebook = ttk.Notebook(outer)
        notebook.grid(row=0, column=0, sticky="nsew")

        general_tab = ttk.Frame(notebook, padding=12)
        fen_tab     = ttk.Frame(notebook, padding=12)
        gains_tab   = ttk.Frame(notebook, padding=12)
        hvac_tab    = ttk.Frame(notebook, padding=12)
        details_tab = ttk.Frame(notebook, padding=12)

        notebook.add(general_tab, text="General")
        notebook.add(fen_tab,     text="Fenestration")
        notebook.add(gains_tab,   text="Gains")
        notebook.add(hvac_tab,    text="HVAC")
        notebook.add(details_tab, text="Details")

        self._build_general_tab(general_tab)
        self._build_fenestration_tab(fen_tab)
        self._build_gains_tab(gains_tab)
        self._build_hvac_tab(hvac_tab)
        self._build_details_tab(details_tab)

        # ── Generate button (shared, below tabs) ──────────────────────────────
        self.generate_btn = ttk.Button(outer, text="Generate", command=self._submit)
        self.generate_btn.grid(row=1, column=0, pady=(12, 0))

        # ── Progress log (shared, below button) ───────────────────────────────
        ttk.Separator(outer, orient="horizontal").grid(
            row=2, column=0, sticky="ew", pady=(12, 4))

        log_frame = ttk.Frame(outer)
        log_frame.grid(row=3, column=0, sticky="nsew")
        outer.rowconfigure(3, weight=1)
        log_frame.columnconfigure(0, weight=1)

        ttk.Label(log_frame, text="Progress:").grid(row=0, column=0, sticky="nw", pady=4)
        self.log_text = tk.Text(log_frame, width=60, height=10, wrap="word",
                                state="disabled", background="#f0f0f0")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.grid(row=0, column=1, sticky="nsew", pady=4)
        log_scroll.grid(row=0, column=2, sticky="ns", pady=4)
        log_frame.columnconfigure(1, weight=1)

        self._on_layout_change()

    # ── General tab ───────────────────────────────────────────────────────────

    def _build_general_tab(self, frame):
        for i in range(4):
            frame.columnconfigure(i, weight=1)
        row = 0

        # Weather file
        ttk.Label(frame, text="Weather file:").grid(row=row, column=0, sticky="w", pady=4)
        self.epw_var = tk.StringVar(value=_DEFAULT_EPW)
        ttk.Entry(frame, textvariable=self.epw_var, width=30).grid(
            row=row, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Button(frame, text="Browse…", command=self._browse_epw).grid(
            row=row, column=3, sticky="w", padx=(8, 0))
        row += 1

        # Location 
        ttk.Label(frame, text="Location:").grid(row=row, column=0, sticky="w", pady=4)
        self.location_var = tk.StringVar(value=defaults["location"])
        ttk.Entry(frame, textvariable=self.location_var, width=30).grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        row += 1

        # Age
        ttk.Label(frame, text="Building age:").grid(row=row, column=0, sticky="w", pady=4)
        self.age_var = tk.StringVar(value=defaults["age"])
        ttk.Entry(frame, textvariable=self.age_var, width=30).grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        row += 1

        # Layout + image
        ttk.Label(frame, text="Building layout:").grid(row=row, column=0, sticky="w", pady=4)
        self.layout_var = tk.StringVar(value=defaults["layout"])
        layout_cb = ttk.Combobox(frame, textvariable=self.layout_var, values=LAYOUTS,
                                 state="readonly", width=33)
        layout_cb.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        layout_cb.bind("<<ComboboxSelected>>", self._on_layout_change)

        self._photo = None
        self.image_label = tk.Label(frame)
        self.image_label.grid(row=row, column=3, rowspan=2, padx=(8, 0), sticky="nw")
        row += 2

        # Primary dimensions
        fl_width = 10
        ttk.Label(frame, text="a (m):").grid(row=row, column=0, sticky="w", pady=4)
        self.a_var = tk.StringVar(value=defaults["a"])
        ttk.Entry(frame, textvariable=self.a_var, width=fl_width).grid(row=row, column=1, sticky="w")

        ttk.Label(frame, text="b (m):").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        self.b_var = tk.StringVar(value=defaults["b"])
        ttk.Entry(frame, textvariable=self.b_var, width=fl_width).grid(row=row, column=3, sticky="w")
        row += 1

        # Secondary dimensions
        self.c_label = ttk.Label(frame, text="c (m):")
        self.c_label.grid(row=row, column=0, sticky="w", pady=4)
        self.c_var = tk.StringVar(value="")
        self.c_entry = ttk.Entry(frame, textvariable=self.c_var, width=fl_width)
        self.c_entry.grid(row=row, column=1, sticky="w")

        self.d_label = ttk.Label(frame, text="d (m):")
        self.d_label.grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        self.d_var = tk.StringVar(value="")
        self.d_entry = ttk.Entry(frame, textvariable=self.d_var, width=fl_width)
        self.d_entry.grid(row=row, column=3, sticky="w")
        row += 1

        # Orientation of side a
        ttk.Label(frame, text="Orientation of side a:").grid(row=row, column=0, sticky="w", pady=4)
        self.orientation_var = tk.StringVar(value=defaults["orientation"])
        orientation_cb = ttk.Combobox(
            frame, textvariable=self.orientation_var,
            values=["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
            state="readonly", width=fl_width-3,
        )
        orientation_cb.grid(row=row, column=1, sticky="w", pady=4)

        # Above-ground floors
        ttk.Label(frame, text="Above-ground floors:").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        self.floors_var = tk.StringVar(value=defaults["above_gnd_floors"])
        ttk.Spinbox(frame, textvariable=self.floors_var, from_=1, to=50, width=fl_width-2).grid(
            row=row, column=3, sticky="w")
        row += 1
        
        # Ceiling height
        ttk.Label(frame, text="Ceiling height (m):").grid(row=row, column=0, sticky="w", pady=4)
        self.ceiling_var = tk.StringVar(value=defaults["ceiling_height"])
        ttk.Entry(frame, textvariable=self.ceiling_var, width=fl_width).grid(row=row, column=1, sticky="w")

        # Basement floors
        ttk.Label(frame, text="Basement floors:").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        self.bsmnt_var = tk.StringVar(value=defaults["basement_floors"])
        ttk.Spinbox(frame, textvariable=self.bsmnt_var, from_=1, to=50, width=8).grid(
            row=row, column=3, sticky="w")
        row += 1

    # ── Fenestration tab ──────────────────────────────────────────────────────

    def _build_fenestration_tab(self, frame):
        frame.columnconfigure(1, weight=1)
        row = 0

        # WWR
        ttk.Label(frame, text="WWR (0–1):").grid(row=row, column=0, sticky="w", pady=4)
        self.wwr_var = tk.StringVar(value=defaults["WWR"])
        wwr_entry = ttk.Entry(frame, textvariable=self.wwr_var, width=10)
        wwr_entry.grid(row=row, column=1, sticky="w")
        wwr_entry.bind("<KeyRelease>", self._on_wwr_typed)
        row += 1

        # WWR images — 3 selectable image tiles
        ttk.Label(frame, text="Or choose the most relevant facade:").grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(10, 4))
        row += 1

        self.wwr_slct_var = tk.StringVar(value=FENESTRATION_TYPES[1][0])  # default: middle tile
        self._fen_photos = []
        self._fen_frames = []

        tiles_frame = ttk.Frame(frame)
        tiles_frame.grid(row=row, column=0, columnspan=4, sticky="w")
        row += 1

        for i, (name, img_path) in enumerate(FENESTRATION_TYPES):
            container = tk.Frame(tiles_frame, bd=2, cursor="hand2")
            container.grid(row=0, column=i, padx=(0, 12), pady=4)
            self._fen_frames.append((name, container))

            photo = None
            if os.path.exists(img_path):
                img = Image.open(img_path)
                img.thumbnail((120, 100))
                photo = ImageTk.PhotoImage(img)
            self._fen_photos.append(photo)

            img_lbl = tk.Label(container, image=photo,
                               text=name if not photo else "",
                               width=120, height=80, bg="#e0e0e0")
            img_lbl.pack(padx=4, pady=(4, 0))
            name_lbl = tk.Label(container, text=name, font=("", 8))
            name_lbl.pack(padx=4, pady=(2, 4))

            for w in (container, img_lbl, name_lbl):
                w.bind("<Button-1>", lambda _, n=name: self._on_fen_select(n))

        self._refresh_fen_selection()

        # Fenestration details
        ttk.Label(frame, text="Fenestration details:").grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(12, 2))
        row += 1
        self.fen_text = tk.Text(frame, width=50, height=5, wrap="word")
        self.fen_text.insert("1.0", defaults["fenestration_description"])
        self.fen_text.grid(row=row, column=0, columnspan=4, sticky="nsew")
        frame.rowconfigure(row, weight=1)

    def _on_fen_select(self, name: str):
        # assigns the value of wwr_slct_var to wwr_var
        self.wwr_slct_var.set(name)
        try:
            self.wwr_var.set(float(name.split()[-1]))
        except ValueError:
            pass
        self._refresh_fen_selection()

    def _refresh_fen_selection(self):
        # makes photos selection
        selected = self.wwr_slct_var.get()
        for name, container in self._fen_frames:
            if name == selected:
                container.config(relief="solid", bg="#cce5ff")
                for child in container.winfo_children():
                    child.config(bg="#cce5ff")
            else:
                container.config(relief="flat", bg="#f0f0f0")
                for child in container.winfo_children():
                    try:
                        child.config(bg="#f0f0f0")
                    except tk.TclError:
                        pass

    def _on_wwr_typed(self, _):
        # when user types in the WWR field --> updates images selection
        val = self.wwr_var.get().strip()
        for name, _ in FENESTRATION_TYPES:
            try:
                if float(name.split()[-1]) == float(val):
                    self.wwr_slct_var.set(name)
                    self._refresh_fen_selection()
                    return
            except ValueError:
                pass
        # typed value doesn't match any tile → clear selection
        self.wwr_slct_var.set("")
        self._refresh_fen_selection()

    # ── Gains tab ─────────────────────────────────────────────────────────────

    def _build_gains_tab(self, frame):
        for i in range(3):
            frame.columnconfigure(i, weight=1)

        fields = [
            ("People", "people_text",    defaults["people_description"]),
            ("Lighting", "lighting_text", defaults["lighting_description"]),
            ("Equipment", "equip_text",   defaults["equipment_description"]),
        ]
        row=0
        for i, (label, attr, placeholder) in enumerate(fields):
            ttk.Label(frame, text=label + ":").grid(row=row, column=0, sticky="w", pady=(8, 0))
            row += 1
            text = tk.Text(frame, width=50, height=4, wrap="word")
            text.insert("1.0", defaults.get(label.lower() + "_description", "") or placeholder)
            text.grid(row=row, column=0,columnspan=3, sticky="ew", pady=(0, 4))
            row += 1
            setattr(self, attr, text)

        self.occ_start_wd  = tk.StringVar(value=defaults["occ_start_wd"])
        self.occ_end_wd    = tk.StringVar(value=defaults["occ_end_wd"])
        self.occ_start_sat = tk.StringVar(value=defaults["occ_start_sat"])
        self.occ_end_sat   = tk.StringVar(value=defaults["occ_end_sat"])
        self.occ_start_sun = tk.StringVar(value=defaults["occ_start_sun"])
        self.occ_end_sun   = tk.StringVar(value=defaults["occ_end_sun"])

        schedule_frame = ttk.Frame(frame)
        schedule_frame.grid(row=row, column=0, columnspan=4, sticky="w")

        def add_schedule(start_row, title, day_vars):
            ttk.Label(schedule_frame, text=title, font=("", 9, "bold")).grid(
                row=start_row, column=0, columnspan=4, sticky="w", pady=(12, 2))
            ttk.Label(schedule_frame, text="Start (h):").grid(row=start_row + 1, column=1, sticky="w", pady=1)
            ttk.Label(schedule_frame, text="End (h):").grid(row=start_row + 1, column=2, sticky="w", pady=1)
            for i, (day_label, var_start, var_end) in enumerate(day_vars):
                r = start_row + 2 + i
                ttk.Label(schedule_frame, text=day_label + ":").grid(row=r, column=0, sticky="w", pady=2, padx=(0, 24))
                ttk.Entry(schedule_frame, textvariable=var_start, width=8).grid(row=r, column=1, sticky="w", padx=(4, 24))
                ttk.Entry(schedule_frame, textvariable=var_end, width=8).grid(row=r, column=2, sticky="w", padx=(4, 0))
        
        add_schedule(0, "Occupancy schedule", [
            ("Weekdays",  self.occ_start_wd,  self.occ_end_wd),
            ("Saturdays", self.occ_start_sat, self.occ_end_sat),
            ("Sundays",   self.occ_start_sun, self.occ_end_sun),
        ])
    # ── HVAC tab ──────────────────────────────────────────────────────────────

    def _build_hvac_tab(self, frame):
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        def add_row(parent_row, label, var1, label1, var2, label2):
            ttk.Label(frame, text=label, font=("", 9, "bold")).grid(
                row=parent_row, column=0, columnspan=4, sticky="w", pady=(12, 2))
            ttk.Label(frame, text=label1 + ":").grid(row=parent_row + 1, column=0, sticky="w", pady=2)
            ttk.Entry(frame, textvariable=var1, width=8).grid(row=parent_row + 1, column=1, sticky="w", padx=(4, 16))
            ttk.Label(frame, text=label2 + ":").grid(row=parent_row + 1, column=2, sticky="w", pady=2)
            ttk.Entry(frame, textvariable=var2, width=8).grid(row=parent_row + 1, column=3, sticky="w", padx=(4, 0))

        def add_schedule(start_row, title, day_vars):
            ttk.Label(frame, text=title, font=("", 9, "bold")).grid(
                row=start_row, column=0, columnspan=4, sticky="w", pady=(12, 2))
            ttk.Label(frame, text="Start (h):").grid(row=start_row + 1, column=1, sticky="w", pady=1)
            ttk.Label(frame, text="End (h):").grid(row=start_row + 1, column=3, sticky="w", pady=1)
            for i, (day_label, var_start, var_end) in enumerate(day_vars):
                r = start_row + 2 + i
                ttk.Label(frame, text=day_label + ":").grid(row=r, column=0, sticky="w", pady=2)
                ttk.Entry(frame, textvariable=var_start, width=8).grid(row=r, column=1, sticky="w", padx=(4, 16))
                ttk.Entry(frame, textvariable=var_end, width=8).grid(row=r, column=3, sticky="w", padx=(4, 0))

        self.occ_heat_sp   = tk.StringVar(value=defaults["occ_heat_sp"])
        self.occ_cool_sp   = tk.StringVar(value=defaults["occ_cool_sp"])
        self.unocc_heat_sp = tk.StringVar(value=defaults["unocc_heat_sp"])
        self.unocc_cool_sp = tk.StringVar(value=defaults["unocc_cool_sp"])

        self.hvac_start_wd  = tk.StringVar(value=defaults["hvac_start_wd"])
        self.hvac_end_wd    = tk.StringVar(value=defaults["hvac_end_wd"])
        self.hvac_start_sat = tk.StringVar(value=defaults["hvac_start_sat"])
        self.hvac_end_sat   = tk.StringVar(value=defaults["hvac_end_sat"])
        self.hvac_start_sun = tk.StringVar(value=defaults["hvac_start_sun"])
        self.hvac_end_sun   = tk.StringVar(value=defaults["hvac_end_sun"])

        

        add_row(0, "Occupied setpoints",   self.occ_heat_sp,   "Heating (°C)", self.occ_cool_sp,   "Cooling (°C)")
        add_row(2, "Unoccupied setpoints", self.unocc_heat_sp, "Heating (°C)", self.unocc_cool_sp, "Cooling (°C)")

        add_schedule(4, "HVAC operation schedule", [
            ("Weekdays",  self.hvac_start_wd,  self.hvac_end_wd),
            ("Saturdays", self.hvac_start_sat, self.hvac_end_sat),
            ("Sundays",   self.hvac_start_sun, self.hvac_end_sun),
        ])

        

        ttk.Label(frame, text="Zones per floor:").grid(row=14, column=0, sticky="w", pady=(12, 2))
        self.zones_var = tk.StringVar(value=defaults["zones_per_floor"])
        ttk.Combobox(frame, textvariable=self.zones_var,
                     values=["1 zone", "2 zones", "5 zones"],
                     state="readonly", width=12).grid(row=14, column=1, sticky="w", pady=(12, 2))

        ttk.Label(frame, text="AHU for ...").grid(row=14, column=2, sticky="w", pady=(12, 2))
        self.ahus_var = tk.StringVar(value="whole building")
        ttk.Combobox(frame, textvariable=self.ahus_var,
                     values=["whole building", "each floor", "perimeter zones + core zones", "each facade + core zones"],
                     state="readonly", width=24).grid(row=14, column=3, sticky="w", pady=(12, 2))

        ttk.Label(frame, text="HVAC details:").grid(row=15, column=0, columnspan=4, sticky="w", pady=(12, 2))
        self.hvac_text = tk.Text(frame, width=50, height=5, wrap="word")
        self.hvac_text.insert("1.0", defaults["hvac_description"])
        self.hvac_text.grid(row=16, column=0, columnspan=4, sticky="nsew", pady=(0, 4))
        frame.rowconfigure(16, weight=1)


    # ── Details tab ───────────────────────────────────────────────────────────

    def _build_details_tab(self, frame):
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text="Additional details:").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.details_text = tk.Text(frame, width=60, height=16, wrap="word")
        self.details_text.grid(row=1, column=0, sticky="nsew")
        self.details_text.insert("1.0", defaults["details"])

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _browse_epw(self):
        path = filedialog.askopenfilename(
            title="Select weather file",
            filetypes=[("EnergyPlus weather", "*.epw"), ("All files", "*.*")],
            initialdir="input_files",
        )
        if path:
            self.epw_var.set(os.path.relpath(path))

    def _on_layout_change(self, *_):
        needs_secondary = SECONDARY_DIMS_REQUIRED[self.layout_var.get()]
        state = "normal" if needs_secondary else "disabled"
        self.c_entry.config(state=state)
        self.d_entry.config(state=state)
        if not needs_secondary:
            self.c_var.set("")
            self.d_var.set("")
        self._update_image()

    def _update_image(self):
        img_path = LAYOUT_IMAGES.get(self.layout_var.get(), "")
        if img_path and os.path.exists(img_path):
            img = Image.open(img_path)
            img.thumbnail((180, 180))
            self._photo = ImageTk.PhotoImage(img)
            self.image_label.config(image=self._photo)
        else:
            self.image_label.config(image="")

    def _parse_float(self, var: tk.StringVar, name: str) -> float:
        try:
            return float(var.get())
        except ValueError:
            raise ValueError(f"'{name}' must be a number.")

    def _parse_optional_float(self, var: tk.StringVar, name: str) -> Optional[float]:
        val = var.get().strip()
        if not val:
            return None
        try:
            return float(val)
        except ValueError:
            raise ValueError(f"'{name}' must be a number or left blank.")

    def _parse_int(self, var: tk.StringVar, name: str) -> float:
        try:
            return int(var.get())
        except (ValueError, TypeError):
            raise ValueError(f"'{name}' must be a whole number.")

    def _submit(self):
        try:
            epw_file = self.epw_var.get().strip()
            if not epw_file:
                raise ValueError("Please select a weather file.")
            layout = self.layout_var.get()
            a = self._parse_float(self.a_var, "a")
            b = self._parse_float(self.b_var, "b")
            needs_secondary = SECONDARY_DIMS_REQUIRED[layout]
            c = self._parse_optional_float(self.c_var, "c")
            d = self._parse_optional_float(self.d_var, "d")
            if needs_secondary and (c is None or d is None):
                raise ValueError(f"Dimensions c and d are required for {layout}.")
            ceiling_height = self._parse_float(self.ceiling_var, "Ceiling height")
            floors = self._parse_int(self.floors_var, "Above-grade floors")
            basement = self._parse_int(self.bsmnt_var, "Basement floors")
            wwr = self._parse_float(self.wwr_var, "WWR")
            if not 0 < wwr < 1:
                raise ValueError("WWR must be between 0 and 1 (exclusive).")
            details = self.details_text.get("1.0", "end").strip()

            occ_heat_sp   = self._parse_float(self.occ_heat_sp,   "Occupied heating setpoint")
            occ_cool_sp   = self._parse_float(self.occ_cool_sp,   "Occupied cooling setpoint")
            unocc_heat_sp = self._parse_float(self.unocc_heat_sp, "Unoccupied heating setpoint")
            unocc_cool_sp = self._parse_float(self.unocc_cool_sp, "Unoccupied cooling setpoint")
            hvac_start_wd  = self.hvac_start_wd.get().strip()
            hvac_end_wd    = self.hvac_end_wd.get().strip()
            hvac_start_sat = self.hvac_start_sat.get().strip()
            hvac_end_sat   = self.hvac_end_sat.get().strip()
            hvac_start_sun = self.hvac_start_sun.get().strip()
            hvac_end_sun   = self.hvac_end_sun.get().strip()
            occ_start_wd   = self.occ_start_wd.get().strip()
            occ_end_wd     = self.occ_end_wd.get().strip()
            occ_start_sat  = self.occ_start_sat.get().strip()
            occ_end_sat    = self.occ_end_sat.get().strip()
            occ_start_sun  = self.occ_start_sun.get().strip()
            occ_end_sun    = self.occ_end_sun.get().strip()
            location    = self.location_var.get().strip()
            age         = self.age_var.get().strip()
            orientation = self.orientation_var.get()
        except ValueError as exc:
            messagebox.showerror("Input error", str(exc))
            return

        self.result = {
            "epw_file": epw_file, "layout": layout,
            "a": a, "b": b, "c": c, "d": d,
            "ceiling_height": ceiling_height,
            "number_of_floors": floors,
            "basement_floors": basement,
            "WWR": wwr,
            "fenestration_description": self.fen_text.get("1.0", "end").strip(),
            "details": details,
            "location": location,
            "age": age,
            "orientation": orientation,
            "people_description":   self.people_text.get("1.0", "end").strip(),
            "lighting_description": self.lighting_text.get("1.0", "end").strip(),
            "equipment_description": self.equip_text.get("1.0", "end").strip(),
            "hvac_description": self.hvac_text.get("1.0", "end").strip(),
            "occ_heat_sp": occ_heat_sp, 
            "occ_cool_sp": occ_cool_sp,
            "unocc_heat_sp": unocc_heat_sp, 
            "unocc_cool_sp": unocc_cool_sp,
            "hvac_start_wd": hvac_start_wd, 
            "hvac_end_wd": hvac_end_wd,
            "hvac_start_sat": hvac_start_sat, 
            "hvac_end_sat": hvac_end_sat,
            "hvac_start_sun": hvac_start_sun, 
            "hvac_end_sun": hvac_end_sun,
            "occ_start_wd": occ_start_wd, 
            "occ_end_wd": occ_end_wd,
            "occ_start_sat": occ_start_sat, 
            "occ_end_sat": occ_end_sat,
            "occ_start_sun": occ_start_sun, 
            "occ_end_sun": occ_end_sun,
            "zones_per_floor": self.zones_var.get(), 
            "AHUs": self.ahus_var.get(),
        }

        self.generate_btn.config(state="disabled")

        def log(msg=""):
            # schedules self._append_log(str(msg) + "\n") to be called on the main (GUI) thread
            # root.after() hand work back to the main thread's event loop
            # 0ms: run as soon as main thread event loop is free
            self.root.after(0, self._append_log, str(msg) + "\n")

        if self.on_submit:
            # Main thread: Tkinter event loop, keeps the GUI responsive
            # Worker thread: runs run_workflow(self.results,log), calls log(...) to send  messages back to GUI 
            # daemon=True — if the user closes the window, Python doesn't wait the thread to finish before exiting
            threading.Thread(target=self.on_submit, args=(self.result, log), daemon=True).start()
        else:
            self.root.destroy()

    def _append_log(self, msg: str):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg)
        self.log_text.see("end")
        self.log_text.config(state="disabled")


def run_with_gui(workflow_fn) -> None:
    """Open the tabbed input form; on submit runs workflow_fn(description, log) in a background thread."""
    root = tk.Tk()
    BuildingInputGUI(root, on_submit=workflow_fn)
    root.mainloop()


def get_building_description() -> dict:
    """Open the GUI, block until the user submits, and return the description dict."""
    root = tk.Tk()
    app = BuildingInputGUI(root)
    root.mainloop()
    if app.result is None:
        raise RuntimeError("GUI closed without submitting a building description.")
    return app.result


if __name__ == "__main__":
    desc = get_building_description()
    print(desc)
    