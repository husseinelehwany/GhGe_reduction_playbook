import os
import sys
import json
from time import time

from ghge_modeller_app import run_with_gui
from ai_bem_workflow import BuildingEnergyWorkflow
from model_checking import ModelChecking


ghge_modeller = BuildingEnergyWorkflow("gemini")


def run_workflow(user_description: dict):
    epw_file = user_description.pop("epw_file")
    print(user_description)

    prompt = ghge_modeller.create_prompt(user_description)
    var_names = ["Site Outdoor Air Drybulb Temperature", "Zone Mean Air Temperature"]
    meter_names = ["Heating:EnergyTransfer", "Cooling:EnergyTransfer", "Electricity:Facility"]
    models_count = 0
    success = False
    model_props = None
    user_def_props = None
    percent_error = None

    for _ in range(3):  # spec compliance loop
        for _ in range(4):  # executability loop
            models_count += 1
            start = time()
            print(f"{'-'*60}\nBot: Thinking...\n trial no: {models_count}\n")
            ghge_modeller.llm_generate_idf(prompt, models_count)
            print("Time taken: ", time() - start)

            print("Bot: executing simulation...\n")
            idf_path = os.path.join(ghge_modeller.workflow_dir, f"llm_gen_model_{models_count}.idf")
            success = ghge_modeller.run_energyplus(idf_path, epw_file)
            if success:
                print("Simulation executed successfully\n")
                print(f"Done.\n{'-' * 60}\n")
                break
            else:
                print("Simulation failed.\n")

            print("Bot: checking errors...\n")
            errors = ghge_modeller.read_error_file()
            print(errors)
            if len(errors) > 0:
                prompt = ghge_modeller.create_error_prompt(errors)
                ghge_modeller.error_parser.delete()
            else:
                ghge_modeller.error_parser.delete()
                break

        if success:
            print("Bot: adding internal gains...\n")
            ghge_modeller.add_internal_gains(user_description, idf_path)

            ghge_modeller.add_output_objects(idf_path, var_names, meter_names)

            print("Bot: adding HVAC components...\n")
            ghge_modeller.add_hvac_templates(user_description, idf_path)
            print("Bot: executing simulation...\n")
            success = ghge_modeller.run_energyplus(idf_path, epw_file)

        if success:
            try:
                my_check = ModelChecking(
                    os.path.join(ghge_modeller.workflow_dir, "eplustbl.csv"),
                    os.path.join(ghge_modeller.workflow_dir, "eplusout.csv"),
                    os.path.join(ghge_modeller.workflow_dir, "eplusmtr.csv"),
                    os.path.join(ghge_modeller.workflow_dir, "eplusout.eio"),
                )
                model_props = my_check.get_envelope_props()
                print(f"Model geometrical specs: {model_props}\n")
                meters = my_check.get_meters()
                print(meters)
            except Exception:
                print("model specs: error found\n")

            user_def_props = ghge_modeller.get_groundtruth(building_description=user_description)
            print(f"User defined specs: {user_def_props}\n")
            percent_error, _ = my_check.get_anomalous_specs(model_props, user_def_props, tolerance=10)
            print(percent_error)
            if percent_error:
                prompt = ghge_modeller.create_specs_prompt(user_description, percent_error)
            else:
                break
        else:
            print("No more possible trials. Try different input prompt.\n")
            break

    # Save results
    results_summary = {
        "success": success,
        "model_props": model_props,
        "user_def_props": user_def_props,
        "percent_error": percent_error,
    }
    with open(os.path.join(ghge_modeller.workflow_dir, "results_summary.json"), "w") as f:
        json.dump(results_summary, f, indent=4)
    ghge_modeller.save_chat_history()
    ghge_modeller.save_outputs()
    print("Done. Results saved.\n")


run_with_gui(run_workflow)
