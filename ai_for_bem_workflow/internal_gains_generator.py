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
        self.idf_path = idf_path
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

    def occupancy_schedule(self, people_dict, name="Occupancy Schedule"):
        """
        Build a Schedule:Compact (fraction 0/1) from the people dict fields:
          occupancy_start  – HH:MM 24-h start time
          occupancy_end    – HH:MM 24-h end time
          occupied_days    – list of day names (Monday … Sunday)

        Day-type logic:
          Mon–Sun  → AllDays          (no unoccupied-day block needed)
          Mon–Fri  → Weekdays / Weekends for the off-days
          Sat–Sun  → Weekends / Weekdays for the off-days
          anything else → individual day names joined by space,
                          then AllOtherDays at 0 for the rest
        """
        start = people_dict["occupancy_start"]   # e.g. "08:00"
        end   = people_dict["occupancy_end"]     # e.g. "18:00"
        days  = set(people_dict["occupied_days"])

        ALL_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday",
                    "Friday", "Saturday", "Sunday"}
        WEEKDAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
        WEEKENDS = {"Saturday", "Sunday"}

        if days == ALL_DAYS:
            occupied_str   = "AllDays"
            unoccupied_str = None
        elif days == WEEKDAYS:
            occupied_str   = "Weekdays"
            unoccupied_str = "Weekends"
        elif days == WEEKENDS:
            occupied_str   = "Weekends"
            unoccupied_str = "Weekdays"
        else:
            day_order = ["Monday", "Tuesday", "Wednesday",
                         "Thursday", "Friday", "Saturday", "Sunday"]
            occupied_str   = " ".join(d for d in day_order if d in days)
            unoccupied_str = "AllOtherDays" if days != ALL_DAYS else None

        fields = {}
        idx = 1

        fields[f"Field_{idx}"] = "Through: 12/31"; idx += 1

        # --- occupied-days block ---
        fields[f"Field_{idx}"] = f"For: {occupied_str}"; idx += 1
        if start != "00:00":
            fields[f"Field_{idx}"] = f"Until: {start}"; idx += 1
            fields[f"Field_{idx}"] = 0;                  idx += 1
        fields[f"Field_{idx}"] = f"Until: {end}"; idx += 1
        fields[f"Field_{idx}"] = 1;               idx += 1
        if end != "24:00":
            fields[f"Field_{idx}"] = "Until: 24:00"; idx += 1
            fields[f"Field_{idx}"] = 0;              idx += 1

        # --- unoccupied-days block ---
        if unoccupied_str:
            fields[f"Field_{idx}"] = f"For: {unoccupied_str}"; idx += 1
            fields[f"Field_{idx}"] = "Until: 24:00";            idx += 1
            fields[f"Field_{idx}"] = 0;                         idx += 1

        self.idf.newidfobject(
            "SCHEDULE:COMPACT",
            Name=name,
            Schedule_Type_Limits_Name="Fraction",
            **fields,
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
            self.idf.idfobjects["PEOPLE"][-1].Name = "Occupancy Schedule"
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

    def add_gains_to_idf(self, building_description: str) -> None:
        """
        Full pipeline: parse description → generate EnergyPlus objects → save IDF.
        Call this from external workflows instead of chaining individual methods.
        """
        print("InternalGainsGenerator: parsing description...")
        json_response = self.generate_internal_gains_request(building_description)
        print(f"InternalGainsGenerator: received gains data: {json.dumps(json_response)}")

        people_dict = json_response.get("people", {})
        lights_dict = json_response.get("lights", {})
        equipment_dict = json_response.get("electric_equipment", {})

        if people_dict:
            self.occupancy_schedule(people_dict)
            self.build_people_obj(people_dict)
        if lights_dict:
            self.build_lights_obj(lights_dict)
        if equipment_dict:
            self.build_electric_equipment_obj(equipment_dict)

        self.idf.save(self.idf_path)
        print(f"InternalGainsGenerator: saved to {self.idf_path}")


def main() -> None:
    idf_file = os.path.join("input_files","shoebox_test_mcp.idf")
    my_gains = InternalGainsGenerator(idf_file)
    loads_description = "A retail building with that has 20 m2/person with energy-saving lights. The working hours are from 12:00 to 22:00 on all days except Sundays. The building has 2 printers and 1 pc."
    json_response = my_gains.generate_internal_gains_request(loads_description)
    print(json.dumps(json_response))
    with open("internal_gains.json", "w") as f:
        json.dump(json_response, f, indent=2)
    people_dict = json_response.get("people", {})
    lights_dict = json_response.get("lights", {})
    equipment_dict = json_response.get("electric_equipment", {})
    my_gains.occupancy_schedule(people_dict)
    my_gains.build_people_obj(people_dict)
    my_gains.build_lights_obj(lights_dict)
    my_gains.build_electric_equipment_obj(equipment_dict)

if __name__ == "__main__":
    main()
