from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import os
from eppy import modeleditor
from eppy.modeleditor import IDF
from api_clients import *

idd_file = "C:\EnergyPlusV24-1-0\Energy+.idd"
IDF.setiddname(idd_file)

class HVACTemplateMCP:
    """
    This class reads energyplus errors from the .err file
    parse: reads .err file
    get_severe_fatal: gets severe and fatal errors

    It returns the errors in json format and saves them to json file for future retrieval
    """

    def __init__(self, idf_path):
        self.request_client = GeminiChats("gemini-2.5-flash")
        self.idf = IDF(idf_path)
        request_template_path = os.path.join("input_files", "request_schema.json")
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
                 f"for the user input. give the output in the format of the schema, do not start and end with ``` or the word JSON. The user input: {building_description}"
        # TODO: check if the request string starts with {
        HVAC_template_request = json.loads(self.request_client.call_client(prompt))
        print(HVAC_template_request)
        return HVAC_template_request

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

    def generate_eplus_objects(self, hvac_template):
        """
        sends the template to its relevant function, generates the energyplus HVAC_TEMPLATE objects and saves file
        :param hvac_template: relevant template
        :return out_idf: updated idf file
        """
        if hvac_template["template_id"] == "Packaged_VAV":
            self.generate_packaged_VAV(hvac_template)
        elif hvac_template["template_id"] == "Heat_pump_air2air":
            self.generate_heat_pump(hvac_template)

    def save_idf(self):
        self.idf.save()  # there is also saveas(newfile) option

    def generate_packaged_VAV(self, template):

        # enable sizing
        if len(self.idf.idfobjects["SIMULATIONCONTROL"]) == 0:
            self.idf.newidfobject("SIMULATIONCONTROL")

        self.idf.idfobjects["SIMULATIONCONTROL"][-1].Do_Zone_Sizing_Calculation = "Yes"
        self.idf.idfobjects["SIMULATIONCONTROL"][-1].Do_System_Sizing_Calculation = "Yes"
        self.idf.idfobjects["SIMULATIONCONTROL"][-1].Do_Plant_Sizing_Calculation = "Yes"
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

        # get zone names
        zone_names = []
        for zone_obj in self.idf.idfobjects["ZONE"]:
            zone_names.append(zone_obj.Name)

        thermostat_name = "thermostat"
        self.idf.newidfobject("HVACTEMPLATE:THERMOSTAT")

        self.idf.idfobjects["HVACTEMPLATE:THERMOSTAT"][-1].Name = thermostat_name
        self.idf.idfobjects["HVACTEMPLATE:THERMOSTAT"][-1].Heating_Setpoint_Schedule_Name = ""
        self.idf.idfobjects["HVACTEMPLATE:THERMOSTAT"][-1].Constant_Heating_Setpoint = 20
        self.idf.idfobjects["HVACTEMPLATE:THERMOSTAT"][-1].Cooling_Setpoint_Schedule_Name = ""
        self.idf.idfobjects["HVACTEMPLATE:THERMOSTAT"][-1].Constant_Cooling_Setpoint = 25

        AHU_name = "AHU1"
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
        for i in range(len(zone_names)):
            self.idf.newidfobject("HVACTEMPLATE:ZONE:VAV")
            self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Zone_Name = zone_names[i]
            self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Template_VAV_System_Name = AHU_name
            self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Template_Thermostat_Name = thermostat_name
            self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Outdoor_Air_Method = "Sum"
            self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Outdoor_Air_Flow_Rate_per_Person = 0.0025
            self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Outdoor_Air_Flow_Rate_per_Zone_Floor_Area = 0.0003
            self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Reheat_Coil_Type = template["fields"]["Reheat_Coil_Type"]
            self.idf.idfobjects["HVACTEMPLATE:ZONE:VAV"][-1].Baseboard_Heating_Type = template["fields"]["Baseboard_Heating_Type"]


    def generate_heat_pump(self, idf, template):
        pass

    def get_hvac_objects(self, building_description):
        # Step 1: LLM creates request
        request = self.generate_HVACTemplate_Request(building_description)
        # Step 2: get hvac template
        hvac_template = self.get_hvac_template(request)
        # step 3: generate hvac_template objects
        self.generate_eplus_objects(hvac_template)
        self.save_idf()

        return self.idf


if __name__ == "__main__":
    building_desc = "AHU system with VAV terminal units without reheat coils and with heat recovery wheel"
    # Initialize MCP provider
    idf = IDF()
    mcp = HVACTemplateMCP(os.path.join("input_files", "shoebox_test_mcp.idf"))
    idf = mcp.get_hvac_objects(building_desc)

