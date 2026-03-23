"""
internal_gains_generator.py
-----------------------------
Graduate-level tool: takes a free-text description of building internal gains
and uses the Anthropic Claude API (with MCP tool-use) to:
  1. Extract structured data into a JSON schema
  2. Auto-generate EnergyPlus IDF objects for:
       - People
       - Lights
       - ElectricEquipment / GasEquipment
       - Schedule:Compact (occupancy, lighting, equipment)
       - ScheduleTypeLimits

Usage
-----
    python internal_gains_generator.py \
        --description "Open-plan office, 50 people, 10 W/m2 lighting, 15 W/m2 equipment" \
        --zone "Zone_Office" \
        --floor-area 500 \
        --output office_gains.idf

Requirements
------------
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...
"""

import argparse
import json
import os
import sys
import textwrap
import ast
from typing import Any
from api_clients import *

from eppy import modeleditor
from eppy.modeleditor import IDF

idd_file = "C:\EnergyPlusV24-1-0\Energy+.idd"
IDF.setiddname(idd_file)

class InternalGainsGenerator:
    """
    This class is an mcp server for internal gains in EnergyPlus.
    idf_path: the idf file to add the internal gains objects

    It returns an idf file after manipulating it and adding people, light, equipment and schedules objects.
    """

    def __init__(self, idf_path):
        self.request_client = OpenRouterAPIClient("google/gemini-3.1-flash-lite-preview")
        self.idf = IDF(idf_path)
        request_template_path = os.path.join("input_files", "internal_gains_schema.json")
        with open(request_template_path, 'r') as file:
            self.request_schema = json.load(file)

    def generate_internal_gains_request(self, building_description):
        prompt = textwrap.dedent(f"""
        You are an expert building energy modeller. Your task is to parse a natural-language
        description of internal gains in a building . Here is the description: {building_description}

        Rules:
        - Give the output in the provided JSON format.
        - Use sensible ASHRAE/IES defaults when a value is not explicitly stated.
        - Express schedule times in HH:MM 24-hour format.
        - Express watts per person as metabolic rate (e.g. 140 W for office work).
        - If the description mentions W/m² for people, convert to number_of_people using the
          provided floor area hint if available; otherwise store in notes.
        """).strip()
        json_response = self.request_client.structured_output(prompt, self.request_schema)
        return ast.literal_eval(json_response)

    def create_zone_list(self):
        # get zone names
        zone_names = []
        for zone_obj in self.idf.idfobjects["ZONE"]:
            zone_names.append(zone_obj.Name)
        if len(self.idf.idfobjects["ZONELIST"]) == 0:
            self.idf.newidfobject("ZONELIST")
            self.idf.idfobjects["ZONELIST"][-1].Name = "all_zones"
            for i in range(len(zone_names)):
                field_name = f"Zone_{i+1}_Name"
                setattr(self.idf.idfobjects["ZONELIST"][-1], field_name, zone_names[i])
            self.idf.save()

    def add_schedule_type_limits(self):
        self.idf.newidfobject("SCHEDULETYPELIMITS",Name="Any Number")
        self.idf.newidfobject(
            "SCHEDULETYPELIMITS",
            Name="Fraction",
            Lower_Limit_Value=0,
            Upper_Limit_Value=1,
            Numeric_Type="Continuous",
        )

    def always_on_schedule(self):
        self.idf.newidfobject(
            "SCHEDULE:COMPACT",
            Name="Always On",
            Schedule_Type_Limits_Name="Fraction",
            Field_1="Through: 12/31",
            Field_2="For: AllDays",
            Field_3="Until: 24:00",
            Field_4=1,
        )

    def activity_schedule(self,name="Office Activity Schedule", activity=120):
        self.idf.newidfobject(
            "SCHEDULE:COMPACT",
            Name=name,
            Schedule_Type_Limits_Name="Any Number",
            Field_1="Through: 12/31",
            Field_2="For: AllDays",
            Field_3="Until: 24:00",
            Field_4=activity,
        )

    def build_people_obj(self, people_dict):
        calculation_method = people_dict["people_density"]["calculation_method"]
        people_value = people_dict["people_density"]["value"]
        activity_level = people_dict["activity_level_W"]
        self.create_zone_list()
        self.add_schedule_type_limits()
        self.always_on_schedule()
        activity_schedule_name = "Activity Schedule"
        self.activity_schedule(activity_schedule_name, activity_level)
        if len(self.idf.idfobjects["PEOPLE"]) == 0:
            self.idf.newidfobject("PEOPLE")
            self.idf.idfobjects["PEOPLE"][-1].Name = "Occupancy"
            self.idf.idfobjects["PEOPLE"][-1].Zone_or_ZoneList_or_Space_or_SpaceList_Name = "all_zones"
            self.idf.idfobjects["PEOPLE"][-1].Number_of_People_Schedule_Name = "Always On"
            self.idf.idfobjects["PEOPLE"][-1].Number_of_People_Calculation_Method = calculation_method # People , People/Area , Area/Person
            if calculation_method == "People":
                self.idf.idfobjects["PEOPLE"][-1].Number_of_People = people_value
            elif calculation_method == "People/Area":
                self.idf.idfobjects["PEOPLE"][-1].People_per_Floor_Area = people_value
            elif calculation_method == "Area/Person":
                self.idf.idfobjects["PEOPLE"][-1].Floor_Area_per_Person = people_value
            self.idf.idfobjects["PEOPLE"][-1].Activity_Level_Schedule_Name = activity_schedule_name

        #TODO: specific zones with different ocupancy
        #TODO: occupancy schedule controlled by API


        # print(self.idf.idfobjects["PEOPLE"][-1].fieldnames)
        # self.idf.idfobjects["ZONELIST"].pop(-1)
        self.idf.save(os.path.join("input_files", "shoebox_test_mcp_modified.idf"))

    def build_lights_obj(self, lights_dict):
        calculation_method = lights_dict["lights_density"]["calculation_method"]
        lights_value = lights_dict["lights_density"]["value"]
        if len(self.idf.idfobjects["LIGHTS"]) == 0:
            self.idf.newidfobject("LIGHTS")
            self.idf.idfobjects["LIGHTS"][-1].Name = "Lights"
            self.idf.idfobjects["LIGHTS"][-1].Zone_or_ZoneList_or_Space_or_SpaceList_Name = "all_zones"
            self.idf.idfobjects["LIGHTS"][-1].Schedule_Name = "Always On"
            self.idf.idfobjects["LIGHTS"][-1].Design_Level_Calculation_Method = calculation_method
            if calculation_method == "LightingLevel":
                self.idf.idfobjects["LIGHTS"][-1].Lighting_Level = lights_value
            elif calculation_method == "Watts/Area":
                self.idf.idfobjects["LIGHTS"][-1].Watts_per_Floor_Area = lights_value
            elif calculation_method == "Watts/Person":
                self.idf.idfobjects["LIGHTS"][-1].Watts_per_Person = lights_value

        self.idf.save(os.path.join("input_files", "shoebox_test_mcp_modified.idf"))

    def build_electric_equipment_obj(self, equipment_dict):
        calculation_method = equipment_dict["electric_equipment_density"]["calculation_method"]
        equipment_value = equipment_dict["electric_equipment_density"]["value"]
        if len(self.idf.idfobjects["ELECTRICEQUIPMENT"]) == 0:
            self.idf.newidfobject("ELECTRICEQUIPMENT")
            self.idf.idfobjects["ELECTRICEQUIPMENT"][-1].Name = "Equipment"
            self.idf.idfobjects["ELECTRICEQUIPMENT"][-1].Zone_or_ZoneList_or_Space_or_SpaceList_Name = "all_zones"
            self.idf.idfobjects["ELECTRICEQUIPMENT"][-1].Schedule_Name = "Always On"
            self.idf.idfobjects["ELECTRICEQUIPMENT"][-1].Design_Level_Calculation_Method = calculation_method
            if calculation_method == "EquipmentLevel":
                self.idf.idfobjects["ELECTRICEQUIPMENT"][-1].Design_Level = equipment_value
            elif calculation_method == "Watts/Area":
                self.idf.idfobjects["ELECTRICEQUIPMENT"][-1].Watts_per_Floor_Area = equipment_value
            elif calculation_method == "Watts/Person":
                self.idf.idfobjects["ELECTRICEQUIPMENT"][-1].Watts_per_Person = equipment_value

        self.idf.save(os.path.join("input_files", "shoebox_test_mcp_modified.idf"))

def main() -> None:
    idf_file = os.path.join("input_files","shoebox_test_mcp.idf")
    my_gains = InternalGainsGenerator(idf_file)
    loads_description = "A medium activity office with an area of 1000 m2 that has 20 m2 per person with florescent lights and a PC for each employee. Thw wroking hours are eight to nine."
    json_response = my_gains.generate_internal_gains_request(loads_description)
    print(json_response)

    people_dict = json_response.get("people", {})
    lights_dict = json_response.get("lights", {})
    equipment_dict = json_response.get("electric_equipment", {})
    my_gains.build_people_obj(people_dict)
    my_gains.build_lights_obj(lights_dict)
    my_gains.build_electric_equipment_obj(equipment_dict)

if __name__ == "__main__":
    main()
