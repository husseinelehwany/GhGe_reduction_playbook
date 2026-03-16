#!/usr/bin/env python3
"""
Building Energy Modeling Workflow using LLMs
==========================================

This workflow uses Claude API to generate EnergyPlus IDF files from textual building descriptions,
runs EnergyPlus simulations, and visualizes results.

Author: AI Assistant
Date: 2024
"""

import os
import sys
import json
import ast
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import logging
from datetime import datetime
import numpy as np
import shutil
sys.path.insert(0, 'C:\EnergyPlusV24-1-0')  # add E-Plus directory to path to be able to import API
from pyenergyplus.api import EnergyPlusAPI
from api_clients import *
from eppy import modeleditor
from eppy.modeleditor import IDF
from chat_history import *
from error_parser import ErrorParser
from mcp_provider import HVACTemplateMCP

idd_file = "C:\EnergyPlusV24-1-0\Energy+.idd"
IDF.setiddname(idd_file)

class BuildingEnergyWorkflow:
    """
    Main workflow class for building energy modeling using LLMs
    """
    
    def __init__(self, client_type):
        """
        Initialize the workflow
        Args:
            client: LLM API client
            workflow_dir: path to store outputs
            template_prompt
        """
        self.workflow_dir = "energy_workflow_output"
        os.makedirs(self.workflow_dir, exist_ok=True)
        # self.chat_history = ChatHistory(max_messages=10, max_tokens=150000)
        self.client_type = client_type
        model_name = {"gemini": "google/gemini-2.5-pro",
                      "deepseek": "deepseek/deepseek-v3.2-speciale",
                      "claude": "anthropic/claude-sonnet-4.6",
                      "openai": "openai/gpt-5.2-pro",
                      "kimi": "moonshotai/kimi-k2.5",
                      "minimax": "minimax/minimax-m2.5",
                      "qwen": "qwen/qwen3.5-plus-02-15"}
        self.client = OpenRouterAPIClient(model_name[client_type], max_messages=2)
        self.validation_client = OpenRouterAPIClient("google/gemini-2.5-pro")

        with open(os.path.join("input_files", "prompt_template.txt") , 'r') as file:
            self.template_prompt = file.read()

        self.error_parser = ErrorParser()


    def get_user_input(self) -> str:
        """
        Step 1: Get textual input from user describing the building
        Returns: str: Building description from user
        """
        print("\n" + "="*60)

        building_description = input("\nEnter your building description: ").strip()

        return building_description

    def create_prompt(self, building_description: str) -> str:
        """
        Merge input into template prompt for API
        Args: building_description: User's building description
        Returns: str: Complete prompt for API
        """
        with open(os.path.join("input_files", "example_file_prompt.idf") , 'r') as file:
            idf_content = file.read()

        prompt = self.template_prompt.format(building_description=building_description, idf_example=idf_content)
        
        # Save prompt for reference
        prompt_file = os.path.join( self.workflow_dir, "full_prompt.txt")
        with open(prompt_file, 'w') as f:
            f.write(prompt)

        return prompt

    def get_props_from_user_input(self, building_description: str):
        with open(r"input_files/user_building_props_schema.json", 'r') as file:
            user_schema = json.load(file)
        prompt = f"get the building properties of {building_description}. Get the WWR as a number from 0 to 100."
        building_props = self.validation_client.struct_output(prompt, user_schema)
        return ast.literal_eval(building_props)

    def llm_generate_idf(self, prompt: str, i: int) -> str:
        # send message/history to llm
        message = self.client.call_client(prompt)
        # create idf
        file_name = os.path.join(self.workflow_dir, f"llm_gen_model_{i}.idf")
        with open(file_name, "w") as file:
            file.write(message)
        return message

    def add_base_objects(self, idf_path):
        idf = IDF(idf_path)
        if len(idf.idfobjects["VERSION"]) == 0:
            idf.newidfobject("VERSION", Version_Identifier="24.1")
        if len(idf.idfobjects["SIMULATIONCONTROL"]) == 0:
            idf.newidfobject("SIMULATIONCONTROL",
                             Do_Zone_Sizing_Calculation="Yes",
                             Do_System_Sizing_Calculation="Yes",
                             Do_Plant_Sizing_Calculation="Yes",
                             Run_Simulation_for_Sizing_Periods="No",
                             Run_Simulation_for_Weather_File_Run_Periods="Yes",
                             Do_HVAC_Sizing_Simulation_for_Sizing_Periods="Yes")
        if len(idf.idfobjects["TIMESTEP"]) == 0:
            idf.newidfobject("TIMESTEP", Number_of_Timesteps_per_Hour=4)
        if len(idf.idfobjects["RUNPERIOD"]) == 0:
            idf.newidfobject("RUNPERIOD", Name="run_period",
                             Begin_Month=1, Begin_Day_of_Month=1, End_Month=12, End_Day_of_Month=31)
        idf.save()

    def _energyplus_callback_function(self, state):
        pass

    def run_energyplus(self, idf_path: str, epw_file: str) -> Tuple[bool, str]:
        api = EnergyPlusAPI()
        state = api.state_manager.new_state()

        # energyplus model calling point, callback function
        api.runtime.callback_begin_system_timestep_before_predictor(state, self._energyplus_callback_function)

        # run EPlus
        # -x short form to run expandobjects for HVACtemplates. see EnergyPlusEssentials.pdf p16
        cmd_args = ['-w', epw_file, '-d', self.workflow_dir, '-x', idf_path]
        result = api.runtime.run_energyplus(state, cmd_args)
        api.state_manager.delete_state(state)
        success = True if result == 0 else False
        if success:
            print("Simulation executed successfully")
        else:
            print("Simulation failed")
        return success

    def read_error_file(self):
        error_file = os.path.join(self.workflow_dir, 'eplusout.err')
        errors = []
        if os.path.exists(error_file):
            self.error_parser.parse(self.workflow_dir, "eplusout.err")
            self.error_parser.save(self.workflow_dir, "errors_json.json")
            errors = self.error_parser.get_severe_fatal()
            if len(errors) > 0:
                print(errors)
            else:
                print("No errors found.")
        else:
            print("No error file generated.")
        return errors

    def create_error_prompt(self, error_messages):
        combined = [value for d in error_messages for value in d.values()]
        errors_str = ", ".join(combined)
        prompt = f"Following errors occured after running the IDF file: {errors_str}. Fix errors and provide ONLY the" \
                 f" IDF file content, starting with the first object and ending with the last object. " \
                 f"Do not include explanation."
        return prompt

    def create_specs_prompt(self,building_description, perc_error):
        perc_error_str = {k: f"{v}%" for k, v in perc_error.items()}
        prompt = f"For this building description {building_description}, you provided the previous model." \
                 f"The model runs succesfully, but some specs deviate from the user definition. " \
                 f"This is the percentage error in the specs {perc_error_str}. Update existing objects without " \
                 f"adding any new objects. Provide ONLY the IDF file content, starting with the first object and " \
                 f"ending with the last object. Do not include explanation."
        return prompt

    def add_hvac_templates(self, building_desc, idf_path):
        mcp = HVACTemplateMCP(idf_path)
        idf = mcp.get_hvac_objects(building_desc)
        return idf

    def add_output_objects(self, idf_path, var_names, meter_names):
        idf = IDF(idf_path)
        idf.newidfobject("OUTPUT:TABLE:SUMMARYREPORTS", Report_1_Name="AllSummary")
        idf.newidfobject("OUTPUTCONTROL:FILES", Output_CSV="Yes")
        idf.newidfobject("OUTPUT:DIAGNOSTICS", Key_1="DisplayExtrawarnings")
        for var in var_names:
            idf.newidfobject(
                "OUTPUT:VARIABLE",
                Key_Value="*",
                Variable_Name=var,
                Reporting_Frequency="Hourly"
            )
        for mtr in meter_names:
            idf.newidfobject(
                "OUTPUT:METER",
                Key_Name=mtr,
                Reporting_Frequency="Hourly"
            )
        idf.save()

    def save_chat_history(self):
        file_name = os.path.join(self.workflow_dir, "full_history.json")
        self.client.save_history(file_name)

    def save_outputs(self):
        """
        saves simulation outputs under results folder, then emptys workflow_dir
        :return:
        """
        dir_num = 1
        target_dir = "results/v1"
        while os.path.exists(target_dir):
            dir_num += 1
            target_dir = f"results/v{dir_num}"
        os.makedirs(target_dir, exist_ok=True)
        shutil.copytree(self.workflow_dir, target_dir, dirs_exist_ok=True)
        # empty workflowdir to avoid future clash
        for filename in os.listdir(self.workflow_dir):
            os.remove(os.path.join(self.workflow_dir, filename))

    def run_workflow(self) -> bool:
        """
        Run the complete workflow
        
        Returns:
            bool: True if workflow completed successfully
        """


        # Step 1: Get user input
        building_description = self.get_user_input()

        # Step 2: Create prompt
        prompt = self.create_prompt(building_description)

        # Step 3: Generate IDF
        for i in range(4):
            print("=" * 60)
            print(f"trial no: {i + 1}")
            model = self.llm_generate_idf(prompt, i)
            # Step 4: Run EnergyPlus
            idf_path = os.path.join(self.workflow_dir, f"llm_gen_model_{i}.idf")
            success = self.run_energyplus(idf_path, self.epw_file)
            if success:
                break
            # check for errors
            errors = self.read_error_file(os.path.join(self.workflow_dir))
            if len(errors) > 0:
                print("="*60)
                prompt = self.create_error_prompt(errors)
            else:  # no errors
                break

        # save history & copy files
        self.save_chat_history()
        self.save_outputs()

        return success

def main():
    # Initialize workflow
    epw_path = os.path.join("input_files", 'Ottawa_CWEC_2020.epw')
    workflow = BuildingEnergyWorkflow("gemini")
    # Run workflow
    # success = workflow.run_workflow()
    bldg_desc = "L-shaped building, the longer edge is 16-by-6m and the shorter edge is 9 by 5m. It is a single-storey with 3.4m ceiling height. It has 50% WWR. It is modelled as single zone with envelope relevant for Ottawa building built in 2020. it has AHU VAV system."
    output = workflow.get_props_from_user_input(bldg_desc)
    print(output)

if __name__ == "__main__":
    main()
