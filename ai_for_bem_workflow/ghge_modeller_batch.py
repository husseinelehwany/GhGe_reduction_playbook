from time import time


from ai_bem_workflow import *
from model_checking import ModelChecking


epw_file = os.path.join("input_files", 'Ottawa_CWEC_2020.epw')
ghge_modeller = BuildingEnergyWorkflow("gemini")

# message = "L-shaped building, the longer edge is 16-by-6m and the shorter edge is 9 by 5m. It is a single-storey with 3.4m ceiling height. It has 50% WWR. It is modelled as single zone with envelope relevant for Ottawa building built in 2020. it has AHU VAV system."
# message = "The building footprint is 35 m wide and 30 m long in a T-shaped configuration single storey, single zone. The top bar measures 35 m wide by 12 m deep. " \
#           "The central stem projects 18 m downward from the midpoint of the top bar and is 9 m wide. It has 40% WWR. " \
#           "the envelope is relevant for Ottawa building built in 2020. it has AHU VAV system"
# message = "a 5-by-5m small office building with 4m ceiling height and a 2-by-2m south facing window."
# message = "a 50 by 33m 3-storey building and floor height of 4m. It has 33% WWR with continuous glazing on all sides. the envelope is relevant for Vancouver building built in 2013. it has AHU VAV system. create perimeter zones and core zone in each floor."
# message = "5 by 5m single room with ceiling height 4m and no windows. it has ahu vav system"
message = "a 28 by 19 m building and height of 3m. It has 21% WWR with windows on all sides. create perimeter zones and core zone in each floor. the envelope is relevant for Ottawa building built in 2022. it has AHU VAV system"
ghge_modeller.epw_file = os.path.join("input_files", 'CAN_ON_Ottawa.716280_CWEC.epw')

enable_llm_loop = True  # used for testing
enable_hvac = True

for i in range(1):
    # Step 2: Create prompt
    prompt = ghge_modeller.create_prompt(message)
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
            # Step 6: add outputs
            ghge_modeller.add_output_objects(idf_path, var_names, meter_names)

            # Step 7: add HVAC, then run model
            if enable_hvac:
                print("Bot: adding HVAC components...\n")
                idf = ghge_modeller.add_hvac_templates(message, idf_path)
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
            user_def_props = ghge_modeller.get_props_from_user_input(message)
            print(f"User defined specs: {user_def_props}\n")
            percent_error, success = my_check.get_anomalous_specs(model_props, user_def_props, tolerance=10)
            print(percent_error)
            if percent_error:
                prompt = ghge_modeller.create_specs_prompt(message, percent_error)
            else:
                break

        else:
            print("No more possible trials. Try different input prompt.\n")
            break



    # Step 9: save chat history and output files
    ghge_modeller.save_chat_history()
    ghge_modeller.save_outputs()
