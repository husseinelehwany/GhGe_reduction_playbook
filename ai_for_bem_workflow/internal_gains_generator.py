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
from typing import Any
from api_clients import *

import anthropic
GAINS_SCHEMA = None

# ---------------------------------------------------------------------------
# MCP Tool definition
# ---------------------------------------------------------------------------

EXTRACT_TOOL: dict[str, Any] = {
    "name": "extract_internal_gains",
    "description": (
        "Extract building internal gains parameters from a natural-language description "
        "and return them as a structured JSON object that matches the provided schema."
    ),
    "input_schema": GAINS_SCHEMA,
}

# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

class InternalGainsGenerator:
    """
    This class is an mcp server for internal gains in EnergyPlus.
    idf_path: the idf file to add the internal gains objects

    It returns an idf file after manipulating it and adding people, light, equipment and schedules objects.
    """

    def __init__(self, idf_path=None):
        self.request_client = OpenRouterAPIClient("google/gemini-3.1-flash-lite-preview")
        request_template_path = os.path.join("input_files", "internal_gains_schema2.json")
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
        response = self.request_client.structured_output(prompt, self.request_schema)
        return response

def main() -> None:
    my_gains = InternalGainsGenerator()
    loads_description = "A medium activity office with an area of 1000 m2 that has 0.1 persons per squared meter with florescent lights and a PC for each employee. Thw wroking hours are eight to nine."
    json_response = my_gains.generate_internal_gains_request(loads_description)
    print(json_response)

if __name__ == "__main__":
    main()
