import os
import json
from time import time

from ghge_desktop_app import run_with_gui
from ai_bem_workflow import BuildingEnergyWorkflow
from model_checking import ModelChecking


ghge_modeller = BuildingEnergyWorkflow("gemini")

def prep_log(in_dict):
    return json.dumps({k: round(v, 2) for k, v in in_dict.items()}, indent=2)

def run_workflow(user_description: dict, log=print):
    epw_file = user_description.pop("epw_file")

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
            log(f"{'-'*50}\nBot: Thinking...  trial no: {models_count}")
            try:
                model = ghge_modeller.llm_generate_idf(prompt, models_count)
            except:
                log("LLM API failure!")
                continue
            log(f"Time taken: {time() - start:.1f}s")

            log("Bot: executing simulation...")
            idf_path = os.path.join(ghge_modeller.workflow_dir, f"llm_gen_model_{models_count}.idf")
            success = ghge_modeller.run_energyplus(idf_path, epw_file)
            if success:
                log("Simulation executed successfully")
                log(f"Done.\n{'-' * 50}")
                ###############################################
                # TODO breaks before checking for warnings !!!!
                ###############################################
                break
            else:
                log("Simulation failed.")

            log("Bot: checking errors...")
            errors = ghge_modeller.read_error_file()
            print(errors)
            if len(errors) > 0:
                log("Bot: Errors found! Debugging errors...")
                prompt = ghge_modeller.create_error_prompt(errors)
                ghge_modeller.error_parser.delete()
            else:
                ghge_modeller.error_parser.delete()
                break

        if success:
            log("Bot: adding internal gains...")
            ghge_modeller.add_internal_gains(user_description, idf_path)
            ghge_modeller.add_output_objects(idf_path, var_names, meter_names)

            log("Bot: adding HVAC components...")
            ghge_modeller.add_hvac_templates(user_description, idf_path)
            log("Bot: executing simulation...")
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
                log(f"Model geometrical specs: {prep_log(model_props)}")
                meters = my_check.get_meters()
                log(f"Meters [kWh/m^2]: {prep_log(meters)}")
            except Exception:
                log("model specs: error found")

            user_def_props = ghge_modeller.get_groundtruth(building_description=user_description)
            log(f"User defined specs: {prep_log(user_def_props)}")
            percent_error, _ = my_check.get_anomalous_specs(model_props, user_def_props, tolerance=10)
            log(f"Percentage error [%]: {prep_log(percent_error)}")
            if percent_error:
                compliant = False
                log("Bot: Model not compliant with user input!")
                prompt = ghge_modeller.create_specs_prompt(user_description, percent_error)
            else:
                compliant = True
                break
        else:
            log("No more possible trials. Try different input prompt.")
            break

    # Save results
    overall_success = success and compliant
    results_summary = {
        "success": overall_success,
        "model_props": model_props,
        "user_def_props": user_def_props,
        "percent_error": percent_error,
    }
    with open(os.path.join(ghge_modeller.workflow_dir, "results_summary.json"), "w") as f:
        json.dump(results_summary, f, indent=4)
    
    ghge_modeller.save_chat_history()
    ghge_modeller.save_outputs()
    log("Done. Results saved.")

    log("Summary:")
    log(f"Success: {overall_success}")
    log(f"Model geometrical specs: {prep_log(model_props)}")
    log(f"User defined specs:: {prep_log(user_def_props)}")
    log(f"Percentage error [%]: {prep_log(percent_error)}")



run_with_gui(run_workflow)
