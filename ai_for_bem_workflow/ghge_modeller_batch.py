import json
from time import time


from ai_bem_workflow import *
from model_checking import ModelChecking
from internal_gains_generator import InternalGainsGenerator


epw_file = os.path.join("input_files", 'Ottawa_CWEC_2020.epw')
ghge_modeller = BuildingEnergyWorkflow("gemini")
user_description = {"layout": "L-shaped building", "a":16, "b":9, "c": 11, "d":3, "ceiling_height":3.4,
                    "number_of_floors":1, "WWR": 0.5, "details": "It is modelled as single zone with envelope relevant for Ottawa building built in 2020. it has AHU VAV system."}
# user_description = {"layout": "T-shaped building", "a":35, "b":12, "c": 18, "d":9, "ceiling_height":4,
#                     "number_of_floors":1, "WWR": 0.4, "details": "Divide the 2 parts of the T-shape into 2 zones. the envelope is relevant for Ottawa building built in 2020. it has AHU VAV system"}
# user_description = {"layout": "Rectangular building", "a":28, "b":19, "c": None, "d":None, "ceiling_height":3,
#                     "number_of_floors":1, "WWR": 0.21,
#                     "details": "Divide the model into perimeter zones and core zone. the envelope is relevant for Ottawa building built in 2022. it has AHU VAV system"}
ghge_modeller.epw_file = os.path.join("input_files", 'CAN_ON_Ottawa.716280_CWEC.epw')

internal_gains_description = (
    "Open-plan office building, 10 m2/person, standard office lighting at 10 W/m2, "
    "and office equipment at 15 W/m2. Occupied Monday to Friday from 08:00 to 18:00."
)

enable_llm_loop = True  # used for testing
enable_hvac = True

for i in range(1):
    # Step 2: Create prompt
    prompt = ghge_modeller.create_prompt(user_description)
    var_names = ["Site Outdoor Air Drybulb Temperature", "Zone Mean Air Temperature"]
    meter_names = ["Heating:EnergyTransfer", "Cooling:EnergyTransfer","Electricity:Facility","NaturalGas:Facility"]
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
            # Step 5.5: add internal gains
            print("Bot: adding internal gains...\n")
            gains_gen = InternalGainsGenerator(idf_path)
            gains_gen.add_gains_to_idf(user_description)

            # Step 6: add outputs
            ghge_modeller.add_output_objects(idf_path, var_names, meter_names)

            # Step 7: add HVAC, then run model
            if enable_hvac:
                print("Bot: adding HVAC components...\n")
                idf = ghge_modeller.add_hvac_templates(user_description, idf_path)
                print("Bot: executing simulation...\n")
                success = ghge_modeller.run_energyplus(idf_path, epw_file)

        if success:
            # Step 8: compare bldg props and meters
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
            percent_error, success = my_check.get_anomalous_specs(model_props, user_def_props, tolerance=10)
            print(percent_error)
            if percent_error:
                prompt = ghge_modeller.create_specs_prompt(user_description, percent_error)
            else:
                break

        else:
            print("No more possible trials. Try different input prompt.\n")
            break



    # Step 9: save chat history and output files
    ghge_modeller.save_chat_history()
    ghge_modeller.save_outputs()
