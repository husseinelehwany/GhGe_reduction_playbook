from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import os
import random
import ast
from collections import defaultdict
from eppy import modeleditor
from eppy.modeleditor import IDF
from api_clients import *
from config import EPLUS_IDD

IDF.setiddname(EPLUS_IDD)

class HVACTemplateMCP:
    """
    This class reads energyplus errors from the .err file
    parse: reads .err file
    get_severe_fatal: gets severe and fatal errors

    It returns the errors in json format and saves them to json file for future retrieval
    """

    def __init__(self, idf_path, eio_file):
        # self.request_client = GeminiChats("gemini-2.5-flash")
        self.request_client = OpenRouterAPIClient("google/gemini-3.1-flash-lite-preview")
        self.idf = IDF(idf_path)
        self.eio_file = eio_file
        request_template_path = os.path.join("input_files", "hvac_request_schema.json")
        with open(request_template_path, 'r') as file:
            self.request_schema = json.load(file)
        self.hvac_templates = {
            "Packaged_VAV": {
            "template_id": "Packaged_VAV",
            "description": "AHU with terminal VAV units",
            "objects": [
                "HVACTEMPLATE:SYSTEM:PACKAGEDVAV",
                "HVACTEMPLATE:ZONE:VAV"
            ],
            "fields":  {
                "Economizer_Type": "DifferentialDryBulb",
                "Reheat_Coil_Type": "Gas",
                "Baseboard_Heating_Type": "None",
                "heat_recovery_type": "None"
                }
            },

            "Heat_pump_air2air": {
                "template_id": "Heat_pump_air2air",
                "description": "heatpump terminal air units",
                "objects": [
                     "HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR",
                     "HVACTEMPLATE:ZONE:UNITARY"
                 ],
                "fields": {
                    "Economizer_Type": "DifferentialDryBulb",
                    "Baseboard_Heating_Type": "None"
                }
            },

            "CAV_System": {
                "template_id": "CAV_System",
                "description": "Common rooftop units (RTU), AHUs with constant air volume (CAV), or unitary systems.",
                "objects": [
                     "HVACTemplate:System:Unitary",
                     "HVACTEMPLATE:ZONE:UNITARY"
                 ],
                "fields": {
                    "control_zone": "None",
                    "Economizer_Type": "DifferentialDryBulb",
                    "Baseboard_Heating_Type": "None"
                }
            }
        }


    def generate_HVACTemplate_Request(self, building_description):
        """
        give the building description to the LLM along with request_schema to generate request. request only contains
        template_id and some changes overrides to default settings as specified by user. It does not include specifics
        about energyplus objects and their fields. The overrides keys and values should match the names of energyplus
        fields and values.
        :return: request in JSON format, contains template_id and overrides
        """
        prompt = f"given this {self.request_schema}, return the most relevant HVAC template id with the necessary overrides " \
                 f"for the user input. Give the output in the format of the schema, do not start and end with ``` or the word JSON. The user input: {building_description}"\
                 f"Choose Packaged_VAV for systems with variable air volume."\
                 f"Choose CAV_System for common rooftop units (RTU), AHUs with constant air volume (CAV), or unitary systems."\
                 f"Choose Heat_pump_air2air for systems containing heatpumps."\
                 f"If there is no mention of HVAC system, then return False in the exists field."
        # TODO: check if the request string starts with {
        # HVAC_template_request = json.loads(self.request_client.call_client(prompt))
        HVAC_template_request = self.request_client.structured_output(prompt, self.request_schema)
        print(HVAC_template_request)
        return json.loads(HVAC_template_request)

    def get_hvac_template(self, request):
        """
        call the hvac template using the template_id and populate it with the overrides. Each template is unique for an
        HVAC layout. A template contains energyplus objects, relevant fields and zones.
        :param request: request in JSON format received from LLM, contains template_id and overrides
        :return: hvac_template
        """
        hvac_template = self.hvac_templates[request["template_id"]]
        if request.get("overrides"):
            for key, value in request["overrides"].items():
                for k, v in hvac_template["fields"].items():
                    if key.lower() in k.lower() or k.lower() in key.lower():
                        hvac_template["fields"][k] = value
        return hvac_template

    def generate_eplus_objects(self, hvac_template, zone_clusters):
        """
        sends the template to its relevant function, generates the energyplus HVAC_TEMPLATE objects and saves file
        :param hvac_template: relevant template
        :return out_idf: updated idf file
        """
        if hvac_template["template_id"] == "Packaged_VAV":
            self.generate_packaged_VAV(hvac_template, zone_clusters)
        elif hvac_template["template_id"] == "Heat_pump_air2air":
            self.generate_heat_pump(hvac_template, zone_clusters)
        elif hvac_template["template_id"] == "CAV_System":
            self.generate_CAV_System(hvac_template, zone_clusters)


    def save_idf(self):
        self.idf.save()  # there is also saveas(newfile) option

    def create_allzones_list(self):
        zone_names = []
        for zone_obj in self.idf.idfobjects["ZONE"]:
            zone_names.append(zone_obj.Name)

        if len(self.idf.idfobjects["ZONELIST"]) == 0:
            self.idf.newidfobject("ZONELIST")
            self.idf.idfobjects["ZONELIST"][-1].Name = "all_zones"
        
            for i, name in enumerate(zone_names, start=1):
                setattr(self.idf.idfobjects["ZONELIST"][-1], f"Zone_{i}_Name", name)
            
        

    def add_sizing_objects(self):
        # enable sizing
        if len(self.idf.idfobjects["SIMULATIONCONTROL"]) == 0:
            self.idf.newidfobject("SIMULATIONCONTROL")

        self.idf.idfobjects["SIMULATIONCONTROL"][-1].Do_Zone_Sizing_Calculation = "Yes"
        self.idf.idfobjects["SIMULATIONCONTROL"][-1].Do_System_Sizing_Calculation = "Yes"
        self.idf.idfobjects["SIMULATIONCONTROL"][-1].Do_Plant_Sizing_Calculation = "No"
        self.idf.idfobjects["SIMULATIONCONTROL"][-1].Run_Simulation_for_Sizing_Periods = "No"
        self.idf.idfobjects["SIMULATIONCONTROL"][-1].Run_Simulation_for_Weather_File_Run_Periods = "Yes"
        self.idf.idfobjects["SIMULATIONCONTROL"][-1].Do_HVAC_Sizing_Simulation_for_Sizing_Periods = "Yes"

        # add sizing
        self.idf.newidfobject("SIZINGPERIOD:WEATHERFILEDAYS")
        self.idf.idfobjects["SIZINGPERIOD:WEATHERFILEDAYS"][-1].Name = "heating sizing"
        self.idf.idfobjects["SIZINGPERIOD:WEATHERFILEDAYS"][-1].Begin_Month = 1
        self.idf.idfobjects["SIZINGPERIOD:WEATHERFILEDAYS"][-1].Begin_Day_of_Month = 1
        self.idf.idfobjects["SIZINGPERIOD:WEATHERFILEDAYS"][-1].End_Month = 1
        self.idf.idfobjects["SIZINGPERIOD:WEATHERFILEDAYS"][-1].End_Day_of_Month =31
        self.idf.newidfobject("SIZINGPERIOD:WEATHERFILEDAYS")
        self.idf.idfobjects["SIZINGPERIOD:WEATHERFILEDAYS"][-1].Name = "cooling sizing"
        self.idf.idfobjects["SIZINGPERIOD:WEATHERFILEDAYS"][-1].Begin_Month = 7
        self.idf.idfobjects["SIZINGPERIOD:WEATHERFILEDAYS"][-1].Begin_Day_of_Month = 1
        self.idf.idfobjects["SIZINGPERIOD:WEATHERFILEDAYS"][-1].End_Month = 7
        self.idf.idfobjects["SIZINGPERIOD:WEATHERFILEDAYS"][-1].End_Day_of_Month = 31

    def add_thermostat(self, thermostat_name):      
        self.idf.newidfobject("HVACTEMPLATE:THERMOSTAT")
        self.idf.idfobjects["HVACTEMPLATE:THERMOSTAT"][-1].Name = thermostat_name
        self.idf.idfobjects["HVACTEMPLATE:THERMOSTAT"][-1].Heating_Setpoint_Schedule_Name = ""
        self.idf.idfobjects["HVACTEMPLATE:THERMOSTAT"][-1].Constant_Heating_Setpoint = 20
        self.idf.idfobjects["HVACTEMPLATE:THERMOSTAT"][-1].Cooling_Setpoint_Schedule_Name = ""
        self.idf.idfobjects["HVACTEMPLATE:THERMOSTAT"][-1].Constant_Cooling_Setpoint = 25

    def generate_packaged_VAV(self, template, zone_clusters):

        # add sizing
        self.add_sizing_objects()

        # get zone names
        zone_names = []
        for zone_obj in self.idf.idfobjects["ZONE"]:
            zone_names.append(zone_obj.Name)

        thermostat_name = "thermostat"
        self.add_thermostat(thermostat_name)

        for i, zone_cluster in enumerate(zone_clusters):
            AHU_name = f"AHU_{i+1}"
            self.idf.newidfobject("HVACTEMPLATE:SYSTEM:PACKAGEDVAV")
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Name = AHU_name
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].System_Availability_Schedule_Name = ""
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Cooling_Coil_Type = "TwoSpeedDX"
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Cooling_Coil_Availability_Schedule_Name = ""
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Cooling_Coil_Setpoint_Schedule_Name = ""
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Cooling_Coil_Design_Setpoint = 13
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Cooling_Coil_Gross_Rated_Total_Capacity = "autosize"
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Cooling_Coil_Gross_Rated_COP = 3

            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Heating_Coil_Type = "Gas"
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Heating_Coil_Availability_Schedule_Name = ""
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Heating_Coil_Setpoint_Schedule_Name = ""
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Heating_Coil_Design_Setpoint = 18
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Heating_Coil_Capacity = "autosize"
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Gas_Heating_Coil_Efficiency = 0.8

            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Economizer_Type = template["fields"]["Economizer_Type"]
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Night_Cycle_Control = "StayOff"
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"][-1].Heat_Recovery_Type = template["fields"]["heat_recovery_type"]

            # TODO: assumption that all zones are conditioned
            for zone in zone_cluster:
                self.idf.newidfobject("HVACTEMPLATE:ZONE:VAV")
                self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Zone_Name = zone
                self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Template_VAV_System_Name = AHU_name
                self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Template_Thermostat_Name = thermostat_name
                self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Outdoor_Air_Method = "Sum"
                self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Outdoor_Air_Flow_Rate_per_Person = 0.0025
                self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Outdoor_Air_Flow_Rate_per_Zone_Floor_Area = 0.0003
                self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Reheat_Coil_Type = template["fields"]["Reheat_Coil_Type"]
                self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Baseboard_Heating_Type = template["fields"]["Baseboard_Heating_Type"]


    def generate_heat_pump(self, template, zone_clusters):
        # add sizing
        self.add_sizing_objects()

        # get zone names
        zone_names = []
        for zone_obj in self.idf.idfobjects["ZONE"]:
            zone_names.append(zone_obj.Name)

        thermostat_name = "thermostat"
        self.add_thermostat(thermostat_name)
        
        for i, zone_cluster in enumerate(zone_clusters):
            system_name = f"HP_{i+1}"
            ctrl_zone = random.choice(zone_clusters[i])
            self.idf.newidfobject("HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR")
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Name = system_name
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].System_Availability_Schedule_Name = "Always On"
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Control_Zone_or_Thermostat_Location_Name = ctrl_zone
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Cooling_Coil_Type = "SingleSpeedDX"
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Heat_Pump_Heating_Coil_Type = "SingleSpeedDXHeatPump"
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Economizer_Type = template["fields"]["Economizer_Type"]
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARYHEATPUMP:AIRTOAIR"][-1].Night_Cycle_Control = "StayOff"

            # TODO: assumption that all zones are conditioned
            for zone in zone_cluster:
                self.idf.newidfobject("HVACTEMPLATE:ZONE:UNITARY")
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Zone_Name = zone
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Template_Unitary_System_Name = system_name
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Template_Thermostat_Name = thermostat_name
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Outdoor_Air_Method = "Sum"
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Outdoor_Air_Flow_Rate_per_Person = 0.0025
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Outdoor_Air_Flow_Rate_per_Zone_Floor_Area = 0.0003
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Baseboard_Heating_Type = template["fields"]["Baseboard_Heating_Type"]
        

    def generate_CAV_System(self, template, zone_clusters):
        # add sizing
        self.add_sizing_objects()

        # get zone names
        zone_names = []
        for zone_obj in self.idf.idfobjects["ZONE"]:
            zone_names.append(zone_obj.Name)

        thermostat_name = "thermostat"
        self.add_thermostat(thermostat_name)

        for i, zone_cluster in enumerate(zone_clusters):
            system_name = f"RTU_{i+1}"
            ctrl_zone = random.choice(zone_clusters[i])
            self.idf.newidfobject("HVACTEMPLATE:SYSTEM:UNITARY")
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARY"][-1].Name = system_name
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARY"][-1].System_Availability_Schedule_Name = "Always On"
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARY"][-1].Control_Zone_or_Thermostat_Location_Name = ctrl_zone 
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARY"][-1].Cooling_Coil_Type = "SingleSpeedDX"
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARY"][-1].Heating_Coil_Type = "Gas"
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARY"][-1].Economizer_Type = template["fields"]["Economizer_Type"]
            self.idf.idfobjects["HVACTEMPLATE:SYSTEM:UNITARY"][-1].Night_Cycle_Control = "StayOff"

            # TODO: assumption that all zones are conditioned
            for zone in zone_cluster:
                self.idf.newidfobject("HVACTEMPLATE:ZONE:UNITARY")
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Zone_Name = zone
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Template_Unitary_System_Name = system_name
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Template_Thermostat_Name = thermostat_name
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Outdoor_Air_Method = "Sum"
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Outdoor_Air_Flow_Rate_per_Person = 0.0025
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Outdoor_Air_Flow_Rate_per_Zone_Floor_Area = 0.0003
                self.idf.idfobjects["HVACTEMPLATE:ZONE:UNITARY"][-1].Baseboard_Heating_Type = template["fields"]["Baseboard_Heating_Type"]
 

    def get_vertical_zone_clusters(self, zones, tol: float = 0.1):
        bld_min_x = min(z["min_x"] for z in zones)
        bld_max_x = max(z["max_x"] for z in zones)
        bld_min_y = min(z["min_y"] for z in zones)
        bld_max_y = max(z["max_y"] for z in zones)

        def _is_perim(z):
            return (
                abs(z["min_x"] - bld_min_x) < tol or
                abs(z["max_x"] - bld_max_x) < tol or
                abs(z["min_y"] - bld_min_y) < tol or
                abs(z["max_y"] - bld_max_y) < tol
            )
        
        stacks = defaultdict(list)
        for z in zones:
            stacks[(z["cx"], z["cy"])].append(z)
        
        core_group  = []
        perim_groups = []
        for stack in stacks.values():
            names = [z["name"] for z in stack]
            if any(_is_perim(z) for z in stack):
                perim_groups.append(names)
            else:
                core_group.extend(names)

        return core_group, perim_groups

    def perimeter_core_split(self, zones, tol: float = 0.1):
        # return all perimeter zones as 1 cluster + 1 for core zones
        core_group, perim_groups = self.get_vertical_zone_clusters(zones, tol)
        perim_zones_flat = [item for group in perim_groups for item in group]
        all_clusters = [core_group, perim_zones_flat]
        return all_clusters

    def exposure_split(self, zones, tol: float = 0.1):
        # returns the zones in each facade as a separate cluster + 1 for core zones
        core_group, perim_groups = self.get_vertical_zone_clusters(zones, tol)
        all_clusters = [core_group] + perim_groups
        return all_clusters

    def floors_split(self, zones):
        zones_per_floor = defaultdict(list)
        for z in zones:
            zones_per_floor[z["min_z"]].append(z["name"])
        return list(zones_per_floor.values())

    def get_zone_clusters(self, ahu_assig, tol: float = 0.1):
        """Group zones 
        ["whole building", "each floor", "perimeter zones + core zones", "each facade + core zones"]
        """
        zones = []
        def _snap(val):
            return round(float(val) / tol) * tol

        with open(self.eio_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("Zone Information"):
                    continue
                v = [x.strip() for x in line.split(",")]
                zones.append({
                    "name":  v[1],
                    "cx": _snap(v[6]), "cy": _snap(v[7]), "min_z": _snap(v[16]),
                    "min_x": float(v[12]), "max_x": float(v[13]),
                    "min_y": float(v[14]), "max_y": float(v[15]),
                })
        zone_clusters = []
        if ahu_assig == "whole building":
            zone_clusters = [[item["name"] for item in zones]]
        elif ahu_assig == "each floor":
            zone_clusters = self.floors_split(zones)
        elif ahu_assig == "perimeter zones + core zones":
            zone_clusters = self.perimeter_core_split(zones)
        elif ahu_assig == "each facade + core zones":
            zone_clusters = self.exposure_split(zones, tol)

        return zone_clusters

    def get_hvac_objects(self, building_description, ahu_assig):
            # Step 1: LLM creates request, MCP client
            request = self.generate_HVACTemplate_Request(building_description)
            
            if request["HVAC_exists"]:
                # Step 2: get hvac template, MCP server
                hvac_template = self.get_hvac_template(request)
                # step 3: generate hvac_template objects
                zone_clusters = self.get_zone_clusters(ahu_assig)
                self.generate_eplus_objects(hvac_template, zone_clusters)
                self.save_idf()
    
            return self.idf

if __name__ == "__main__":
    building_desc = "AHU system with VAV terminal units without reheat coils and with heat recovery wheel"
    # building_desc = "RTU with basic controls."
    # building_desc = "A building with heatpump system and ventilation."
    building_desc = "A building with 4 rooms and 2 windows."
    # Initialize MCP provider
    idf = IDF()
    mcp = HVACTemplateMCP(os.path.join("test_mcp_HVAC", "llm_gen_model_3.idf"), os.path.join("test_mcp_HVAC","llm_gen_model_3.eio"))
    # idf = mcp.get_hvac_objects(building_desc)
    zone_clusters = mcp.get_zone_clusters("perimeter zones + core zones")
    mcp.generate_eplus_objects(mcp.hvac_templates["CAV_System"], zone_clusters)
    mcp.save_idf()
        
    
    
    

