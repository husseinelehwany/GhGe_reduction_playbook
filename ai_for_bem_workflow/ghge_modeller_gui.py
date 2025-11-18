import tkinter as tk
from tkinter import scrolledtext
import threading
import time
from ai_bem_workflow import *
from model_checking import ModelChecking

class GHGeBotGUI:
    def __init__(self, root, ghge_modeller):
        self.root = root
        self.ghge_modeller = ghge_modeller
        root.title("GHGe Modeller")
        root.geometry("800x600")
        root.configure(bg="#3a3a3a")  #window colour: medium dark grey

        # Chat display, bg boxes colour: darker grey, fg text colour: light grey
        self.chat_display = scrolledtext.ScrolledText(root, height=27, wrap=tk.WORD, state=tk.DISABLED, bg="#2d2d2d",
                                                      fg="#e0e0e0", insertbackground="white")
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # label
        tk.Label(root, text="Enter your building description:", bg="#3a3a3a", fg="#e0e0e0").pack(anchor=tk.W, padx=10)

        # Input
        self.input_text = tk.Text(root, height=3, bg="#2d2d2d", fg="#e0e0e0", insertbackground="white")
        self.input_text.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.input_text.bind("<Return>", lambda e: self.send_message() or "break")

        # Send button
        tk.Button(root, text="Generate", command=self.send_message, bg="#2d2d2d", fg="white").pack(pady=(0, 10))

        # self.append_text(f"Enter your building description: \n")


    def append_text(self, text):
        """
        sends text to chat display
        """
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, text)
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def send_message(self):
        """
        executes process when Generate button pressed. Step 1: Get user input.
        """
        message = self.input_text.get("1.0", tk.END).strip()
        self.input_text.delete("1.0", tk.END)
        threading.Thread(target=self.process, args=(message,), daemon=True).start()

    def process(self, message):
        epw_path = os.path.join("input_files", 'Ottawa_CWEC_2020.epw')
        self.append_text(f"\nYou: {message}\n")

        # Step 2: Create prompt
        prompt = self.ghge_modeller.create_prompt(message)
        bldg_props = self.ghge_modeller.get_props_from_user_input(message)

        for i in range(4):
            # Step 3: Generate IDF
            self.append_text(f"{'-'*60}\nBot: Thinking...\n trial no: {i + 1}\n")
            model = self.ghge_modeller.llm_generate_idf(prompt, i)
            # Step 4: Run EnergyPlus
            self.append_text("Bot: executing simulation...\n")
            idf_path = os.path.join(self.ghge_modeller.workflow_dir, f"llm_gen_model_{i}.idf")
            success = self.ghge_modeller.run_energyplus(idf_path, epw_path)
            # self.ghge_modeller.check_areas(idf_path)
            if success:
                self.append_text("Simulation executed successfully\n")
                self.append_text(f"Done.\n{'-' * 60}\n")
                break
            else:
                self.append_text("Simulation failed.\n")

            # check for errors
            self.append_text("Bot: checking errors...\n")
            errors = self.ghge_modeller.read_error_file()
            # errors = self.ghge_modeller.read_error_file(os.path.join(self.ghge_modeller.workflow_dir))
            self.append_text(errors)
            if len(errors) > 0:
                prompt = self.ghge_modeller.create_error_prompt(errors)
                self.ghge_modeller.error_parser.delete()
            else:  # no severe/fatal errors
                # delete all errors including warnings, to avoid conflicts
                self.ghge_modeller.error_parser.delete()
                break

        if success:
            try:
                my_check = ModelChecking(os.path.join(self.ghge_modeller.workflow_dir, "eplustbl.csv"), "temp", "temp")
                props_model = my_check.get_envelope_props()
                print(props_model)
                self.append_text(f"model geometrical specs: {props_model}\n")
            except Exception as e:
                self.append_text("model specs: error found\n")
            print(f"user defined geometrical specs {bldg_props}")
        else:
            self.append_text("No more possible trials. Try different input prompt.\n")



        self.ghge_modeller.save_chat_history()
        self.ghge_modeller.save_outputs()



epw_file = os.path.join("input_files", 'Ottawa_CWEC_2020.epw')
root = tk.Tk()
ghge_modeller = BuildingEnergyWorkflow("gemini", epw_file)
app = GHGeBotGUI(root, ghge_modeller)
root.mainloop()
