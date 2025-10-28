# This script reads input for the survey
# and generates data in a transferable form to create the idf file
import os
import numpy as np
import pandas as pd
from edit_idf_files import write_idf
from Layouts import *

# envelope
# Internal loads
# HVAC
# output csv or xml

def read_ghge_survey(survey_file):
    df = pd.read_excel("survey_1.xlsx", index_col=0).transpose()
    df.info()
    if df["Shape"][0] in ["rectangle","L-shape"]:
        if df["Shape"][0] == "rectangle":
            rect_layout = RectangularLayout(df["Shape"][0], df["Dimensions"][0], df["Dimensions"][1], df["Height"][0])
            print(rect_layout)
            print(rect_layout.get_surfaces()[1])

    input_idf_file = os.path.join("EPlus_files", "empty_model.idf")
    output_file_name = os.path.join("EPlus_files", "updated_model.idf")
    model_params = {"layout":rect_layout,
                    "envelope":df["Envelope"][0],
                    "people":df["Occupancy"][0],
                    "WWR":df["WWR"][0]}
    write_idf(input_idf_file, model_params, output_file_name)


read_ghge_survey("Survey file")