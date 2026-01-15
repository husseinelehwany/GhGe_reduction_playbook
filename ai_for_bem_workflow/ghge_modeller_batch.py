import time
from ai_bem_workflow import *
from model_checking import ModelChecking


epw_file = os.path.join("input_files", 'Ottawa_CWEC_2020.epw')

ghge_modeller = BuildingEnergyWorkflow("gemini", epw_file)

message = "a 50 by 33m 3-storey building and floor height of 4m. It has 33% WWR with continuous glazing on all sides. the envelope is relevant for Vancouver building built in 2013. it has AHU VAV system"
ghge_modeller.epw_file = os.path.join("input_files", 'Vancouver_CWEC_2020.epw')

for i in range(3):
    # Step 2: Create prompt
    prompt = ghge_modeller.create_prompt(message)
    bldg_props = ghge_modeller.get_props_from_user_input(message)
    var_names = ["Site Outdoor Air Drybulb Temperature", "Zone Mean Air Temperature"]
    meter_names = ["Heating:EnergyTransfer", "Cooling:EnergyTransfer","Electricity:Facility","NaturalGas:Facility"]
    for i in range(4):
        # Step 3: Generate IDF
        print(f"{'-'*60}\nBot: Thinking...\n trial no: {i + 1}\n")
        model = ghge_modeller.llm_generate_idf(prompt, i)
        # Step 4: Run EnergyPlus
        print("Bot: executing simulation...\n")
        idf_path = os.path.join(ghge_modeller.workflow_dir, f"llm_gen_model_{i}.idf")
        success = ghge_modeller.run_energyplus(idf_path)
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
        print("Bot: adding HVAC components...\n")
        idf = ghge_modeller.add_hvac_templates(message, idf_path)
        print("Bot: executing simulation...\n")
        success = ghge_modeller.run_energyplus(idf_path)

    if success:
        # Step 8: compare bldg props and meters
        print(f"user defined geometrical specs {bldg_props}")
        try:
            my_check = ModelChecking(os.path.join(ghge_modeller.workflow_dir, "eplustbl.csv"),
                                     os.path.join(ghge_modeller.workflow_dir, "eplusout.csv"),
                                     os.path.join(ghge_modeller.workflow_dir, "eplusmtr.csv")
                                     )
            props_model = my_check.get_envelope_props()
            print(f"model geometrical specs: {props_model}\n")
            meters = my_check.get_meters()
            print(meters)
        except Exception as e:
            print("model specs: error found\n")
    else:
        print("No more possible trials. Try different input prompt.\n")

    # Step 9: save chat history and output files
    ghge_modeller.save_chat_history()
    ghge_modeller.save_outputs()
