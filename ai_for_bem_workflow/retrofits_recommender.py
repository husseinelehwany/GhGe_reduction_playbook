import os
import sys
import json
from typing import Optional
import re
import warnings
from config import EPLUS_DIR, EPLUS_IDD
sys.path.insert(0, EPLUS_DIR)
from pyenergyplus.api import EnergyPlusAPI
from api_clients import OpenRouterAPIClient
from ecm_catalog import ECMCatalog
from eppy.modeleditor import IDF
from building_properties import *
import random

IDF.setiddname(EPLUS_IDD)


class RetrofitsRecommender:
    def __init__(self, idf_path: str, epw_path: str, client_type: str = "gemini"):
        """
        Args:
            idf_path: path to the baseline EnergyPlus IDF file
            epw_path: path to the weather file (.epw)
            client_type: LLM to use ("gemini", "claude", "deepseek", etc.)
        """
        self.idf_file = idf_path
        self.epw_path = epw_path
        
        model_map = {
                    "gemini": "google/gemini-3.1-pro-preview",
                    "deepseek": "deepseek/deepseek-v4-pro",
                    "claude": "anthropic/claude-opus-4.8",
                    "gpt": "openai/gpt-5.5-pro",
                    "kimi": "moonshotai/kimi-k2.5",
                    "minimax": "minimax/minimax-m2.5",
                    "qwen": "qwen/qwen3.5-plus-02-15"}

        self.client = OpenRouterAPIClient(model_map.get(client_type, model_map["gemini"]))
        self.idf = IDF(idf_path)
        # self.building = Building(EPLUS_IDD, self.idf_file)
        self.api = EnergyPlusAPI()
        self.baseline_results: Optional[dict] = None
        self.retrofit_results: list[dict] = []

        self.catalog = ECMCatalog()
        schema_path = os.path.join("input_files", "ecm_recommendation_schema.json")
        with open(schema_path, "r") as f:
            self.recommendation_schema = json.load(f)

        idf_dir = os.path.dirname(idf_path)
        dir_num = 1
        self.workflow_dir = os.path.join(idf_dir, "v1") 
        while os.path.exists(self.workflow_dir):
            dir_num += 1
            self.workflow_dir = os.path.join(idf_dir, f"v{dir_num}") 
        os.makedirs(self.workflow_dir, exist_ok=True)
        self.output_dir = os.path.join(self.workflow_dir, "out_retrofit")
        self.base_dir = os.path.join(self.workflow_dir, "out_base")

    # ── Simulation ────────────────────────────────────────────────────────────
    def run_simulation(self,idf_path, output_dir) -> bool:
        state = self.api.state_manager.new_state()
        cmd_args = ["-w", self.epw_path, "-d", output_dir, "-x", idf_path]
        result = self.api.runtime.run_energyplus(state, cmd_args)
        self.api.state_manager.delete_state(state)

        success = result == 0
        return success

    def run_retrofit(self) -> bool:
        """Run EnergyPlus on the latest retrofit IDF in workflow_dir."""
        retrofit_files = [
            f for f in os.listdir(self.workflow_dir)
            if f.startswith("retrofit_") and f.endswith(".idf")
        ]
        if not retrofit_files:
            raise FileNotFoundError(f"No retrofit IDF files found in {self.workflow_dir}")

        retrofit_files.sort(key=lambda f: int(f.replace("retrofit_", "").replace(".idf", "")))
        idf_path = os.path.join(self.workflow_dir, retrofit_files[-1])
        print(f"Running simulation on {retrofit_files[-1]}")

        success = self.run_simulation(idf_path, self.output_dir)
        
        print("Simulation completed successfully" if success else "Simulation failed")
        return success

    def run_baseline(self) -> dict:
        """Run simulation on the original IDF and store as baseline."""
        success = self.run_simulation(self.idf_file, self.base_dir)
        return success

    # ── Results ───────────────────────────────────────────────────────────────

    def parse_results(self, output_dir: str) -> dict:
        """Parse EnergyPlus output files (eplusmtr.csv, eplustbl.csv) into a results dict."""
        pass

    def compare_results(self, baseline: dict, retrofitted: dict) -> dict:
        """Compute percent savings for each energy metric."""
        pass

    def save_results(self, results: dict, label: str):
        """Save results dict to JSON in workflow_dir."""
        pass   

    # ── LLM agents ───────────────────────────────────────────────────────────

    def recommend_retrofits(self, goal) -> list[dict]:
        """Select and parameterise ECMs from the catalog given an IDF file.
        Returns a list of recommendation dicts
        """
        with open(self.idf_file, "r", encoding="utf-8", errors="ignore") as f:
            idf_content = f.read()

        catalog_json = json.dumps(self.catalog.get_ecm_list() , indent=2)
        
        prompt = (
            "You are a building energy retrofit expert.\n"
            "Analyse the EnergyPlus IDF file of a building in Ottawa and recommend the most impactful"
            f"Energy Conservation Measures (ECMs) to achieve {goal}. \n\n"
            "Rules:\n"
            "- Select up to 5 ECMs whose ecm_id exists in the ECM catalog.\n"
            "- Assign priority starting at 1 (1 = highest expected savings).\n"
            "- Write a concise rationale explaining why the ECM suits this building.\n"
            "- Provide output in the given schema. \n"
            "- use the instructions dict to make the necessary changes."
            "- if any fields in the instructions dict are empty, then leave the corrosponding fields in the output empty."
            "- investigate the idf file, R-values, infiltration rates, lights, setpoints and schedules."
            "- make sure that the recommended measures improve the model, not the opposite."
            f"ECM Catalog:\n{catalog_json}\n\n"
            f"IDF File:\n{idf_content}"
        )

        message = self.client.structured_output(prompt, self.recommendation_schema)
        self._strip_fences(message)
        message = json.loads(message)
        results = message["results"]
        with open(os.path.join(self.workflow_dir, "ecm_recommendations.json"), "w") as f:
            json.dump(results, f, indent=4)
        return results

    # ── IDF manipulation ─────────────────────────────────────────────────────

    def save_idf(self, file_no):
        self.idf.save(os.path.join(self.workflow_dir, f"retrofit_{file_no}.idf"))

    def apply_wall_insulation(self, ecm):
        for surface in self.idf.idfobjects["BUILDINGSURFACE:DETAILED"]:
            if surface.Surface_Type == "Wall" and surface.Outside_Boundary_Condition == "Outdoors":
                surface.Construction_Name = self.idf.idfobjects["CONSTRUCTION"][-1].Name

    def apply_roof_insulation(self, ecm):
        for surface in self.idf.idfobjects["BUILDINGSURFACE:DETAILED"]:
            if surface.Surface_Type == "Roof" and surface.Outside_Boundary_Condition == "Outdoors":
                surface.Construction_Name = self.idf.idfobjects["CONSTRUCTION"][-1].Name

    def apply_window_upgrade(self, ecm): 
        for surface in self.idf.idfobjects["FENESTRATIONSURFACE:DETAILED"]:
            if surface.Surface_Type == "Window" and self.is_external_wall(surface):
                surface.Construction_Name = self.idf.idfobjects["CONSTRUCTION"][-1].Name   

    def is_external_wall(self, fen_surface) -> bool:
        """Return True if the fenestration surface sits on an exterior wall (Outdoors boundary)."""
        base_name = fen_surface.Building_Surface_Name
        base = [s for s in self.idf.idfobjects["BUILDINGSURFACE:DETAILED"] if s.Name == base_name]
        if not base:
            return False
        return base[0].Surface_Type == "Wall" and base[0].Outside_Boundary_Condition == "Outdoors"


    @staticmethod
    def _normalise_field(name: str) -> str:
        """Replace spaces with underscores to match eppy fieldname format."""
        return name.replace(" ", "_")

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove markdown code fences that some LLMs wrap around IDF output."""
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip())
        text = re.sub(r"\n?```$", "", text.strip())
        return text.strip()

    def update_object(self, ecm):
        "Manipulate specific eplus objects"
        for param in ecm["edit_objects"]:
            obj_name = param["object"]
            field_name = self._normalise_field(param["field"])
            value = param["value"]
            if obj_name in self.idf.idfobjects:
                for object in self.idf.idfobjects[obj_name]:
                    if field_name in object.fieldnames:
                        setattr(object, field_name, value)
                    else:
                        raise KeyError(field_name)
        
    def add_heatpump(self, ecm):        
        system_name = f"HP_1"
        zone_names = [zone.Name for zone in self.idf.idfobjects["ZONE"]]
        ctrl_zone = random.choice(zone_names)
        self.idf.newidfobject("HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR")
        self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Name = system_name
        self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].System_Availability_Schedule_Name = "Always On"
        self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Control_Zone_or_Thermostat_Location_Name = ctrl_zone
        self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Cooling_Coil_Type = "SingleSpeedDX"
        self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Heat_Pump_Heating_Coil_Type = "SingleSpeedDXHeatPump"
        self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Economizer_Type = "DifferentialDryBulb"
        self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Night_Cycle_Control = "CycleOnAny"
        self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Heat_Recovery_Type = "Sensible"

        # TODO: assumption that all zones are conditioned
        thermostat_name = self.idf.idfobjects["HVACTEMPLATE:THERMOSTAT"][-1].Name
        
        for zone in zone_names:
            self.idf.newidfobject("HVACTEMPLATE:ZONE:UNITARY")
            self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Zone_Name = zone
            self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Template_Unitary_System_Name = system_name
            self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Template_Thermostat_Name = thermostat_name
            self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Outdoor_Air_Method = "Sum"
            self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Outdoor_Air_Flow_Rate_per_Person = 0.0025
            self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Outdoor_Air_Flow_Rate_per_Zone_Floor_Area = 0.0003
            self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Baseboard_Heating_Type = "Electric"

    def erase_energyplus_objects(self, obj_list):
        for obj_type in obj_list:
            to_remove = list(self.idf.idfobjects[obj_type.upper()])
            for obj in to_remove:
                self.idf.removeidfobject(obj)

    def add_energyplus_object(self, raw_str):
        objects_str = self.remove_comments(raw_str)
        obj_lst = self.get_individual_objects(objects_str)
        for obj in obj_lst:
            self.insert_eplus_object(obj)
    
    def remove_comments(self, raw_str: str):
        # Strip inline comments (everything from ! onward)
        clean_lines = []
        for line in raw_str.splitlines():
            idx = line.find("!")
            if idx != -1:
                line = line[:idx]
            clean_lines.append(line.strip())

        clean = " ".join(clean_lines).rstrip(";").strip()
        return clean

    def get_individual_objects(self, clean_str: str):
        # Each IDF object ends with ';' — split on it to separate objects
        chunks = [chunk.strip() for chunk in clean_str.split(";") if chunk.strip()]
        return [chunk + ";" for chunk in chunks]

    def insert_eplus_object(self, obj_str: str):
        """Parse a raw IDF text block and insert it into the loaded IDF.

        Strips inline comments, splits on commas, and writes the value list
        directly onto the new eppy object — works for extensible objects like
        Schedule:Compact without fieldnames running out.
        """
        obj_str = obj_str.strip().rstrip(";")
        tokens = [t.strip() for t in obj_str.split(",") if t.strip()]

        obj_type     = tokens[0]
        field_values = tokens[1:]
        obj_name     = field_values[0] if field_values else None

        # Remove existing object with the same name to avoid duplicates
        # in Name field exists
        if obj_name:
            existing = []
            for o in self.idf.idfobjects[obj_type.upper()]:
                if "Name" in o.fieldnames and o.Name == obj_name:
                    existing.append(o)
            for o in existing:
                self.idf.removeidfobject(o)

        new_obj = self.idf.newidfobject(obj_type.upper())
        # Extend in-place for extensible types (e.g. Schedule:Compact)
        while len(new_obj.obj) < 1 + len(field_values):
            new_obj.obj.append("")
        # Write values into the existing list in-place — do NOT rebind new_obj.obj
        for i, val in enumerate(field_values, start=1):
            new_obj.obj[i] = val
        
    def apply_retrofit(self, ecm: dict) -> str:
        """Apply a single retrofit dict to the IDF and save to a new file. Returns new IDF path."""

        if ecm["ecm_id"] in ["wall_insulation", "roof_insulation", "window_upgrade"]:
            if ecm["new_objects"]:
                constructions_before = len(self.idf.idfobjects["CONSTRUCTION"])
                self.add_energyplus_object(ecm["new_objects"])
                constructions_after = len(self.idf.idfobjects["CONSTRUCTION"])
                if constructions_after > constructions_before:
                    const_name = self.idf.idfobjects["CONSTRUCTION"][-1].Name
                    print(f"{const_name} added successfully!")
                else:
                    sys.exit("Fatal error: failed to add new construction.")
            else:
                warnings.warn("LLM did not generate relevant energyplus objects, try again!") 
            if ecm["custom_function"]:
                getattr(self, ecm["custom_function"])(ecm)
            else:
                warnings.warn("LLM did not call the relevant function, try again!") 
        
        elif ecm["ecm_id"] in ["AHU_schedule", "setpoints_setback"]:
            if ecm["new_objects"]:
                schedules_before = len(self.idf.idfobjects["SCHEDULE:COMPACT"])
                self.add_energyplus_object(ecm["new_objects"])
                schedules_after = len(self.idf.idfobjects["SCHEDULE:COMPACT"])
                
                sch_name = self.idf.idfobjects["SCHEDULE:COMPACT"][-1].Name
                print(f"{sch_name} added successfully!")
                
            else:
                warnings.warn("LLM did not generate relevant energyplus objects, try again!") 
            self.update_object(ecm)

        elif ecm["ecm_id"] in ["SAT_reset", "infiltration_reduction", "heat_recovery", "economiser_enable", "DCV", "lighting_upgrade", "electric_coils"]:
            self.update_object(ecm)

        elif ecm["ecm_id"] == "add_heatpump":
            # add schedule
            if ecm["new_objects"]:
                schedules_before = len(self.idf.idfobjects["SCHEDULE:COMPACT"])
                self.add_energyplus_object(ecm["new_objects"])
                schedules_after = len(self.idf.idfobjects["SCHEDULE:COMPACT"])
                
                sch_name = self.idf.idfobjects["SCHEDULE:COMPACT"][-1].Name
                print(f"{sch_name} added successfully!")
                
            else:
                warnings.warn("LLM did not generate relevant energyplus objects, try again!") 
            # add heatpump template
            if ecm["custom_function"]:
                getattr(self, ecm["custom_function"])(ecm)
            # erase older template
            self.erase_energyplus_objects(ecm["erase_objects"])
            # set the schedule
            self.update_object(ecm)

        self.save_idf(ecm["priority"])


    # ── Orchestration ─────────────────────────────────────────────────────────

    def run(self, building_description: str):
        """
        Full pipeline:
          1. run_baseline
          2. recommend_retrofits
          3. For each retrofit: apply_retrofit → run_simulation → parse_results → compare_results
          4. refine_retrofits
          5. summarise_savings
        """
        pass

if __name__ == "__main__":
    root_path = r"C:\Users\Hussein Elehwany\Desktop\Repos\GhGe_reduction_playbook\ai_for_bem_workflow"
    idf_path = os.path.join(root_path, "retrofit models","results", "Lshaped_poor_windows", "model.idf")
    epw_path = os.path.join(root_path, "input_files", "CAN_ON_Ottawa.716280_CWEC.epw")
    

    
    for i in range(4):
        scenario = RetrofitsRecommender(idf_path, epw_path, "gemini")

        # run baseline, --> out_base
        # scenario.run_baseline()

        # get recommendations
        goal =  [ "energy efficiency" , "reduce carbon emissions", "low cost measures" ]
        measures = scenario.recommend_retrofits(goal[0])
        
        for measure in measures:
            print(measure)
            scenario.apply_retrofit(measure)

        # run retrofits
        # scenario.run_retrofit()
    

   