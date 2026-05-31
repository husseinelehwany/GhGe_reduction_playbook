import json
from time import time


from ai_bem_workflow import *
from model_checking import ModelChecking


epw_file = os.path.join("input_files", 'Ottawa_CWEC_2020.epw')
ghge_modeller = BuildingEnergyWorkflow("gemini")
user_description = {"layout": "Rectangular building", "a":24, "b":18, "c": None, "d":None, "ceiling_height":4,
                    "number_of_floors":1, "WWR": 0.33,
                    "details": "It is a small office building. create 4 perimeter zones and 1 core zone. the envelope is relevant for a Toronto building built in 2024. It has occupant density of 30 m2 per occupant, LED lights and common office equipment.  The HVAC system consists of AHU with an economizer and VAV boxes with reheat coils."}

ghge_modeller.epw_file = os.path.join("input_files", 'CAN_ON_Toronto.716240_CWEC.epw')

enable_llm_loop = True  # used for testing
enable_hvac = True

for i in range(1):
    # Step 2: Create prompt
    prompt = ghge_modeller.create_prompt(user_description)
    var_names = ["Site Outdoor Air Drybulb Temperature", "Zone Mean Air Temperature"]
    # TODO: add specialized meters depending on the existing HVAC system
    meter_names = ["Heating:EnergyTransfer", "Cooling:EnergyTransfer","Electricity:Facility"]
    models_count = 0
    for j in range(3):  # spec compliance loop
        for i in range(4):  # executability loop
            # Step 3: Generate IDF
            models_count += 1
            start = time()
            print(f"{'-'*60}\nBot: Thinking...\n trial no: {models_count}\n")
            model = ghge_modeller.llm_generate_idf(prompt, models_count)
            print("Time taken: ", time() - start)
            # Step 4: Run EnergyPlus
            print("Bot: executing simulation...\n")

            idf_path = os.path.join(ghge_modeller.workflow_dir, f"llm_gen_model_{models_count}.idf")
            success = ghge_modeller.run_energyplus(idf_path, epw_file)
            # self.ghge_modeller.check_areas(idf_path)
            if success:
                print("Simulation executed successfully\n")
                print(f"Done.\n{'-' * 60}\n")
                break
            else:
                print("Simulation failed.\n")

            # Step 5: check for errors
            print("Bot: checking errors...\n")
            errors = ghge_modeller.read_error_file()
            # errors = self.ghge_modeller.read_error_file(os.path.join(self.ghge_modeller.workflow_dir))
            print(errors)
            if len(errors) > 0:
                prompt = ghge_modeller.create_error_prompt(errors)
                ghge_modeller.error_parser.delete()
            else:  # no severe/fatal errors
                # delete all errors including warnings, to avoid conflicts
                ghge_modeller.error_parser.delete()
                break

        if success:
            # Step 6: add internal gains
            print("Bot: adding internal gains...\n")
            ghge_modeller.add_internal_gains(user_description, idf_path)

            # Step 7: add outputs
            ghge_modeller.add_output_objects(idf_path, var_names, meter_names)

            # Step 8: add HVAC, then run model
            if enable_hvac:
                print("Bot: adding HVAC components...\n")
                idf = ghge_modeller.add_hvac_templates(user_description, idf_path)
                print("Bot: executing simulation...\n")
                success = ghge_modeller.run_energyplus(idf_path, epw_file)

        if success:
            # Step 9: compare bldg props and meters
            try:
                my_check = ModelChecking(os.path.join(ghge_modeller.workflow_dir, "eplustbl.csv"),
                                         os.path.join(ghge_modeller.workflow_dir, "eplusout.csv"),
                                         os.path.join(ghge_modeller.workflow_dir, "eplusmtr.csv"),
                                         os.path.join(ghge_modeller.workflow_dir, "eplusout.eio")
                                         )
                model_props = my_check.get_envelope_props()
                print(f"Model geometrical specs: {model_props}\n")
                meters = my_check.get_meters()
                print(meters)
            except Exception as e:
                print("model specs: error found\n")
            # get user-defined properties
            # user_def_props = ghge_modeller.get_props_from_user_input(user_description)
            user_def_props = ghge_modeller.get_groundtruth(building_description=user_description)
            print(f"User defined specs: {user_def_props}\n")
            percent_error, success_specs = my_check.get_anomalous_specs(model_props, user_def_props, tolerance=10)
            print(percent_error)
            if percent_error:
                prompt = ghge_modeller.create_specs_prompt(user_description, percent_error)
            else:
                break

        else:
            print("No more possible trials. Try different input prompt.\n")
            break



    # Step 10: save chat history and output files
    results_summary = {
        "success": locals().get("success"),
        "model_props": locals().get("model_props"),
        "user_def_props": locals().get("user_def_props"),
        "percent_error": locals().get("percent_error"),
    }
    with open(os.path.join(ghge_modeller.workflow_dir, "results_summary.json"), "w") as f:
        json.dump(results_summary, f, indent=4)
    ghge_modeller.save_chat_history()
    ghge_modeller.save_outputs()
