import os
import pandas as pd


class ModelChecking:
    def __init__(self, summary_table, variables_file, meters_file):
        """
        class that reads energyplus output files and extracts key info.

        Args:
            summary_table (str): file path
            variables_file (str): file path
            meters_file (str): file path
        """
        self.summary_table = summary_table
        self.variables_file = variables_file
        self.meters_file = meters_file


    def extract_dataframe(self, start_idx, end_idx):
        df = pd.read_csv(
            self.summary_table,
            skiprows=start_idx,
            nrows=end_idx - start_idx - 1,
            header=0
        )
        # Remove the first empty column if it exists
        if df.columns[0] == '' or df.iloc[:,0].isna().all():
            df = df.iloc[:, 1:]
        return df

    def get_envelope_table(self):
        with open(self.summary_table, 'r') as f:
            lines = f.readlines()
        # Find the start of "Opaque Exterior" section
        start_idx = None
        for i, line in enumerate(lines):
            if 'Opaque Exterior' in line:
                # The header is typically 2 lines after the section name
                start_idx = i + 2
                break

        # Find the end of the table (next empty line or next section)
        end_idx = None
        if start_idx:
            for i in range(start_idx + 1, len(lines)):
                # Stop at empty line or next section header
                if lines[i].strip() == '' or lines[i].strip().startswith('Opaque Interior'):
                    end_idx = i
                    break
        # Read the specific section
        if start_idx and end_idx:
            df = self.extract_dataframe(start_idx, end_idx)

        return df

    def get_ground_floor_area(self):
        df_envelope = self.get_envelope_table()
        df_gnd_floor = df_envelope[df_envelope["Construction"] == "GROUND FLOOR"]
        gnd_floor_area = df_gnd_floor["Gross Area [m2]"].sum()
        return gnd_floor_area


    def get_WWR_table(self):
        with open(self.summary_table, 'r') as f:
            lines = f.readlines()
        # Find the start of "Opaque Exterior" section
        start_idx = None
        for i, line in enumerate(lines):
            if 'ENVELOPE' in lines[i-1] and 'Window-Wall Ratio' in line:
                # The header is typically 2 lines after the section name
                start_idx = i + 2
                end_idx = i + 8
                break

        # Read the specific section
        if start_idx and end_idx:
            df = self.extract_dataframe(start_idx, end_idx)

        return df

    def get_WWR(self, WWR_search_key):
        df_wwr = self.get_WWR_table()
        row = df_wwr.loc[df_wwr.iloc[:,0] == WWR_search_key]
        WWR = row["Total"].values[0]
        return WWR

    def get_building_area(self):
        with open(self.summary_table, 'r') as f:
            lines = f.readlines()
        # Find search key
        for i, line in enumerate(lines):
            if 'Building Area' in lines[i-3] and 'Total Building Area' in line:
                parts = line.split(',')  #'4950.00\n'
                total_area = float(parts[-1].strip())
                break
        return total_area

    def get_envelope_props(self):
        single_floor_area = self.get_ground_floor_area()
        WWR = self.get_WWR(r"Above Ground Window-Wall Ratio [%]")
        total_wall_area = self.get_WWR(r"Above Ground Wall Area [m2]")
        total_window_area = self.get_WWR("Window Opening Area [m2]")
        total_floor_area = self.get_building_area()
        return {"single_floor_area": single_floor_area, "WWR": WWR, "total_wall_area": total_wall_area,
                "total_floor_area": total_floor_area, "total_window_area": total_window_area}

def main():
    my_check = ModelChecking("llm_gen_model_1Table2.csv","temp","temp")  #eplustbl
    props_dict = my_check.get_envelope_props()
    print(props_dict)

if __name__ == "__main__":
    main()
