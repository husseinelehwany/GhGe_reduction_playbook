import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional


LAYOUTS = [
    "Rectangular building",
    "L-shaped building",
    "T-shaped building",
    "U-shaped building",
    "Hollow building",
]

SECONDARY_DIMS_REQUIRED = {
    "Rectangular building": False,
    "L-shaped building": True,
    "T-shaped building": True,
    "U-shaped building": True,
    "Hollow building": True,
}

_DEFAULT_EPW = os.path.join("input_files", "CAN_AB_Edmonton.711230_CWEC.epw")

defaults = {
    "layout": "Rectangular building",
    "a": 30.0, "b": 30.0, "c": None, "d": None,
    "ceiling_height": 3.0,
    "number_of_floors": 5,
    "WWR": 0.4,
    "details": "It is a medium office building. create 4 perimeter zones and 1 core zone. the envelope is relevant for an Edmonton building built in 2014."
    " It has 0.05 occupants per m2, LED lights and common office equipment. "
    " The HVAC system consists of AHU with an economizer and heat recovery, VAV boxes with reheat coils and electric baseboard heaters."  #"More details on the building...",
}


class BuildingInputGUI:
    def __init__(self, root: tk.Tk, on_submit=None):
        self.root = root
        self.on_submit = on_submit
        self.result: Optional[dict] = None

        root.title("GHGe Modeller")
        root.resizable(True, True)

        frame = ttk.Frame(root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        row = 0

        # Weather file
        ttk.Label(frame, text="Weather file:").grid(row=row, column=0, sticky="w", pady=4)
        self.epw_var = tk.StringVar(value=_DEFAULT_EPW)
        ttk.Entry(frame, textvariable=self.epw_var, width=30).grid(
            row=row, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Button(frame, text="Browse…", command=self._browse_epw).grid(
            row=row, column=3, sticky="w", padx=(8, 0))
        row += 1

        # Layout
        ttk.Label(frame, text="Building layout:").grid(row=row, column=0, sticky="w", pady=4)
        self.layout_var = tk.StringVar(value=defaults["layout"])
        layout_cb = ttk.Combobox(frame, textvariable=self.layout_var, values=LAYOUTS,
                                 state="readonly", width=22)
        layout_cb.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)
        layout_cb.bind("<<ComboboxSelected>>", self._on_layout_change)
        row += 1

        # Primary dimensions
        ttk.Label(frame, text="a (m):").grid(row=row, column=0, sticky="w", pady=4)
        self.a_var = tk.StringVar(value=defaults["a"])
        ttk.Entry(frame, textvariable=self.a_var, width=10).grid(row=row, column=1, sticky="w")

        ttk.Label(frame, text="b (m):").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        self.b_var = tk.StringVar(value=defaults["b"])
        ttk.Entry(frame, textvariable=self.b_var, width=10).grid(row=row, column=3, sticky="w")
        row += 1

        # Secondary dimensions
        self.c_label = ttk.Label(frame, text="c (m):")
        self.c_label.grid(row=row, column=0, sticky="w", pady=4)
        self.c_var = tk.StringVar(value="")
        self.c_entry = ttk.Entry(frame, textvariable=self.c_var, width=10)
        self.c_entry.grid(row=row, column=1, sticky="w")

        self.d_label = ttk.Label(frame, text="d (m):")
        self.d_label.grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        self.d_var = tk.StringVar(value="")
        self.d_entry = ttk.Entry(frame, textvariable=self.d_var, width=10)
        self.d_entry.grid(row=row, column=3, sticky="w")
        row += 1

        # Ceiling height
        ttk.Label(frame, text="Ceiling height (m):").grid(row=row, column=0, sticky="w", pady=4)
        self.ceiling_var = tk.StringVar(value=defaults["ceiling_height"])
        ttk.Entry(frame, textvariable=self.ceiling_var, width=10).grid(row=row, column=1, sticky="w")
        row += 1

        # Number of floors
        ttk.Label(frame, text="Number of floors:").grid(row=row, column=0, sticky="w", pady=4)
        self.floors_var = tk.StringVar(value=defaults["number_of_floors"])
        ttk.Spinbox(frame, textvariable=self.floors_var, from_=1, to=50, width=8).grid(
            row=row, column=1, sticky="w")
        row += 1

        # WWR
        ttk.Label(frame, text="WWR (0–1):").grid(row=row, column=0, sticky="w", pady=4)
        self.wwr_var = tk.StringVar(value=defaults["WWR"])
        ttk.Entry(frame, textvariable=self.wwr_var, width=10).grid(row=row, column=1, sticky="w")
        row += 1

        # Details
        ttk.Label(frame, text="Details:").grid(row=row, column=0, sticky="nw", pady=4)
        self.details_text = tk.Text(frame, width=40, height=6, wrap="word")
        self.details_text.grid(row=row, column=1, columnspan=3, sticky="ew", pady=4)
        self.details_text.insert("1.0", defaults["details"])
        row += 1

        # Generate button
        self.generate_btn = ttk.Button(frame, text="Generate", command=self._submit)
        self.generate_btn.grid(row=row, column=0, columnspan=4, pady=(12, 0))
        row += 1

        # Progress log
        ttk.Separator(frame, orient="horizontal").grid(
            row=row, column=0, columnspan=5, sticky="ew", pady=(12, 4))
        row += 1
        ttk.Label(frame, text="Progress:").grid(row=row, column=0, sticky="nw", pady=4)
        self.log_text = tk.Text(frame, width=55, height=10, wrap="word",
                                state="disabled", background="#f0f0f0")
        log_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.grid(row=row, column=1, columnspan=3, sticky="nsew", pady=4)
        log_scroll.grid(row=row, column=4, sticky="ns", pady=4)
        frame.rowconfigure(row, weight=1)

        self._on_layout_change()

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
            floors = int(self.floors_var.get())
            wwr = self._parse_float(self.wwr_var, "WWR")
            if not 0 < wwr < 1:
                raise ValueError("WWR must be between 0 and 1 (exclusive).")
            details = self.details_text.get("1.0", "end").strip()
        except ValueError as exc:
            messagebox.showerror("Input error", str(exc))
            return

        self.result = {
            "epw_file": epw_file,
            "layout": layout,
            "a": a,
            "b": b,
            "c": c,
            "d": d,
            "ceiling_height": ceiling_height,
            "number_of_floors": floors,
            "WWR": wwr,
            "details": details,
        }

        # greys out the Generate button and prevents it from being clicked again
        self.generate_btn.config(state="disabled")

        # scheduling a function to run on the main (GUI) thread. in 0 ms, call self._append_log with this arg.
        def log(msg=""):
            self.root.after(0, self._append_log, str(msg) + "\n")

        # creates a second thread runs alongside the main thread.
        # Main thread: [tkinter mainloop], Worker thread: [run_workflow()]  
        if self.on_submit:
            # target=self.on_submit --> run_workflow(user_description, log)
            threading.Thread(target=self.on_submit, args=(self.result, log), daemon=True).start()
        else:
            self.root.destroy()

    def _append_log(self, msg: str):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg)
        self.log_text.see("end")
        self.log_text.config(state="disabled")


def run_with_gui(workflow_fn) -> None:
    """Open the input form; on submit runs workflow_fn(description) in a background thread."""
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
