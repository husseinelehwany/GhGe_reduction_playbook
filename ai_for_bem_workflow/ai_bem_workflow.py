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

idd_file = "C:\EnergyPlusV24-1-0\Energy+.idd"
IDF.setiddname(idd_file)

class BuildingEnergyWorkflow:
    """
    Main workflow class for building energy modeling using LLMs
    """
    
    def __init__(self, client_type, epw_path):
        """
        Initialize the workflow
        Args:
            client: LLM API client
            workflow_dir: path to store outputs
            template_prompt
        """
        self.epw_file = epw_path
        self.workflow_dir = "energy_workflow_output"
        os.makedirs(self.workflow_dir, exist_ok=True)
        self.chat_history = ChatHistory(max_messages=10, max_tokens=150000)
        self.client_type = client_type
        if client_type == "claude":
            self.client = ClaudeAPIClient("claude-sonnet-4-20250514",20000)  # "claude-3-5-haiku-20241022"  # or claude-3-opus-20240229
        elif client_type == "deepseek":
            self.client = DeepseekAPIClient("deepseek-reasoner")  # "deepseek-chat"  "deepseek-reasoner"
        elif client_type == "gemini":
            self.client = GeminiChats("gemini-2.5-pro")  #"gemini-2.5-pro"  "gemini-2.5-flash
        elif client_type == "openai":
            self.client = OpenaiAPIClient("gpt-5")

        with open(os.path.join("input_files", "prompt_template.txt") , 'r') as file:
            self.template_prompt = file.read()


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

    def llm_generate_idf(self, prompt: str, i: int) -> str:
        # save user message to chat history
        self.chat_history.append(role="user",content= prompt)
        # send message/history to llm
        if self.client_type == "gemini":
            message = self.client.call_client(prompt)
        else:
            message = self.client.call_client(self.chat_history.messages)
        # save llm response to chat hsitory
        self.chat_history.append(role="assistant", content=message)
        # create idf
        file_name = os.path.join(self.workflow_dir, f"llm_gen_model_{i}.idf")
        with open(file_name, "w") as file:
            file.write(message)

        return message

    def llm_generate_idf_dummy(self, prompt: str, i: int) -> str:
        self.chat_history.append(role="user", content=prompt)
        with open(os.path.join("input_files", "example_file_prompt.idf") , 'r') as file:
            message = file.read()
        self.chat_history.append(role="assistant", content=message)
        file_name = os.path.join(self.workflow_dir, f"llm_gen_model_{i}.idf")
        with open(file_name, "w") as file:
            file.write(message)

        return message

    def rectangle_area(self, p):
        """
        Calculate area of rectangle in 3D space
        p1, p2, p3, p4: corner coordinates as arrays [x, y, z]
        Assumes p2 and p4 are adjacent to p1
        """
        v1 = p[1] - p[0]
        v2 = p[3] - p[0]
        cross = np.cross(v1, v2)
        return np.linalg.norm(cross)

    def check_areas(self, idf_file):
        idf = IDF(idf_file)
        for surf in idf.idfobjects["BUILDINGSURFACE:DETAILED"]:
            if surf.Number_of_Vertices == 4:
                coordinates = []
                for i in range(4):
                    coordinates.append(
                        [surf["Vertex_{}_Xcoordinate".format(i + 1)], surf["Vertex_{}_Ycoordinate".format(i + 1)],
                         surf["Vertex_{}_Zcoordinate".format(i + 1)]])
                area = self.rectangle_area(np.array(coordinates))
                print("{} area= {} m2".format(surf.Surface_Type, str(area)))
            else:
                print("The function does not support surfaces with more or less that 4 vertices.")

    def _energyplus_callback_function(self, state):
        pass

    def run_energyplus(self, idf_path: str, epw_path: str) -> Tuple[bool, str]:
        api = EnergyPlusAPI()
        state = api.state_manager.new_state()

        # energyplus model calling point, callback function
        api.runtime.callback_begin_system_timestep_before_predictor(state, self._energyplus_callback_function)

        # run EPlus
        # -x short form to run expandobjects for HVACtemplates. see EnergyPlusEssentials.pdf p16
        cmd_args = ['-w', epw_path, '-d', self.workflow_dir, '-x', idf_path]
        result = api.runtime.run_energyplus(state, cmd_args)
        api.state_manager.delete_state(state)
        success = True if result == 0 else False
        if success:
            print("Simulation executed successfully")
        else:
            print("Simulation failed")
        return success

    def read_error_file(self, path):
        # self.workflow_dir, 'out'
        error_file = os.path.join(path, 'eplusout.err')
        error_content = []
        if os.path.exists(error_file):
            with open(error_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line_lower = line.lower()
                    if '** severe  **' in line_lower or '**  fatal  **' in line_lower:
                        error_content.append(line.strip())
            if len(error_content) > 0:
                print(error_content)
            else:
                print("No errors found")
        else:
            print("No error file generated.")
        return error_content

    def read_error_file_dummy(self, path):
        # self.workflow_dir, 'out'
        error_file = os.path.join("input_files", 'error_file_fail.err')
        error_content = []
        if os.path.exists(error_file):
            with open(error_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line_lower = line.lower()
                    if '** severe  **' in line_lower or '**  fatal  **' in line_lower:
                        error_content.append(line.strip())
            if len(error_content) > 0:
                print(error_content)
            else:
                print("No errors found")
        else:
            print("No error file generated.")
        return error_content

    def create_error_prompt(self, error_messages):
        errors_str = ", ".join(error_messages)
        prompt = f"Following errors occured after running the IDF file: {errors_str}. Fix errors and provide ONLY the IDF file content, starting with the first object and ending with the last object. Do not include explanation."
        return prompt

    def save_chat_history(self):
        history = self.chat_history.get()
        file_name = os.path.join(self.workflow_dir, "full_history.json")
        with open(file_name, 'w') as f:
            json.dump(history, f, indent=4)

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

        case = "full_flow"


        if case == "full_flow":
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
                self.check_areas(idf_path)
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
    workflow = BuildingEnergyWorkflow("deepseek", epw_path)
    # Run workflow
    success = workflow.run_workflow()

if __name__ == "__main__":
    main()
