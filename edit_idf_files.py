import numpy as np
import pandas as pd
from eppy import modeleditor
from eppy.modeleditor import IDF
import os

def write_idf(input_idf_file, model_params):
    # Path to the EnergyPlus .idd file
    idd_file = os.path.join("EPlus_files","Energy+.idd")

    # Set up the IDF class to use the IDD file and Read the IDF file
    IDF.setiddname(idd_file)
    idf = IDF(input_idf_file)

    # simulation control
    idf.newidfobject("SIMULATIONCONTROL")
    idf.idfobjects["SIMULATIONCONTROL"][-1].Do_Zone_Sizing_Calculation = "No"
    idf.idfobjects["SIMULATIONCONTROL"][-1].Do_System_Sizing_Calculation = "No"
    idf.idfobjects["SIMULATIONCONTROL"][-1].Do_Plant_Sizing_Calculation = "No"
    idf.idfobjects["SIMULATIONCONTROL"][-1].Run_Simulation_for_Sizing_Periods = "Yes"
    idf.idfobjects["SIMULATIONCONTROL"][-1].Run_Simulation_for_Weather_File_Run_Periods = "Yes"
    idf.idfobjects["SIMULATIONCONTROL"][-1].Do_HVAC_Sizing_Simulation_for_Sizing_Periods = "No"
    idf.idfobjects["SIMULATIONCONTROL"][-1].Maximum_Number_of_HVAC_Sizing_Simulation_Passes = 1

    ## time step
    idf.newidfobject("TIMESTEP")
    idf.idfobjects["TIMESTEP"][-1].Number_of_Timesteps_per_Hour = 1

    ## run period
    idf.newidfobject("RUNPERIOD")
    idf.idfobjects["RUNPERIOD"][-1].Name = "run period"
    idf.idfobjects["RUNPERIOD"][-1].Begin_Month = 1
    idf.idfobjects["RUNPERIOD"][-1].Begin_Day_of_Month = 1
    idf.idfobjects["RUNPERIOD"][-1].End_Month = 12
    idf.idfobjects["RUNPERIOD"][-1].End_Day_of_Month = 31

    ## Materials
    # read materials dict
    df = pd.read_excel("Materials_dict.xlsx")

    # add materials
    for idx, row in df.iterrows():
        # check if material exists
        if len(idf.idfobjects["MATERIAL"]) > 0:
            all_idf_mats = np.array([x.Name for x in idf.idfobjects["MATERIAL"]])
            if not (row["Name"] in all_idf_mats):
                idf.newidfobject("MATERIAL")
                idf.idfobjects["MATERIAL"][-1].Name = row["Name"]
                idf.idfobjects["MATERIAL"][-1].Roughness = row["Roughness"]
                idf.idfobjects["MATERIAL"][-1].Thickness = row["Thickness"]
                idf.idfobjects["MATERIAL"][-1].Conductivity = row["Conductivity"]
                idf.idfobjects["MATERIAL"][-1].Density = row["Density"]
                idf.idfobjects["MATERIAL"][-1].Specific_Heat = row["Specific_Heat"]
        else:
            idf.newidfobject("MATERIAL")
            idf.idfobjects["MATERIAL"][-1].Name = row["Name"]
            idf.idfobjects["MATERIAL"][-1].Roughness = row["Roughness"]
            idf.idfobjects["MATERIAL"][-1].Thickness = row["Thickness"]
            idf.idfobjects["MATERIAL"][-1].Conductivity = row["Conductivity"]
            idf.idfobjects["MATERIAL"][-1].Density = row["Density"]
            idf.idfobjects["MATERIAL"][-1].Specific_Heat = row["Specific_Heat"]

    # Construction
    idf.newidfobject("CONSTRUCTION")
    idf.idfobjects["CONSTRUCTION"][-1].Name = "Exterior Wall"
    idf.idfobjects["CONSTRUCTION"][-1].Outside_Layer = "I01 25mm insulation board"
    idf.idfobjects["CONSTRUCTION"][-1].Layer_2 = ""
    idf.idfobjects["CONSTRUCTION"][-1].Layer_3 = ""

    idf.newidfobject("CONSTRUCTION")
    idf.idfobjects["CONSTRUCTION"][-1].Name = "Exterior Floor"
    idf.idfobjects["CONSTRUCTION"][-1].Outside_Layer = "I01 25mm insulation board"

    idf.newidfobject("CONSTRUCTION")
    idf.idfobjects["CONSTRUCTION"][-1].Name = "Exterior Roof"
    idf.idfobjects["CONSTRUCTION"][-1].Outside_Layer = "I01 25mm insulation board"


    ## Building surface detail
    new_coordinates = [[0,1,0],[0,0,0],[1,0,0],[1,1,0]]
    idf.newidfobject("BUILDINGSURFACE:DETAILED")
    print(idf.idfobjects["BUILDINGSURFACE:DETAILED"][0].fieldnames)
    idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Name = "Exterior Roof"
    idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Surface_Type = "Floor"
    idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Construction_Name = "Exterior Floor"
    idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Zone_Name = "zone1"
    idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Space_Name = ""
    idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Outside_Boundary_Condition = "Adiabatic"
    idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Outside_Boundary_Condition_Object = ""
    idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Sun_Exposure = "NoSun"
    idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Wind_Exposure = "NoWind"
    idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].View_Factor_to_Ground = ""
    idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Number_of_Vertices = len(new_coordinates)

    for i in range(len(new_coordinates)):
        sngl_vrtx = new_coordinates[i]
        idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].update({"Vertex_{}_Xcoordinate".format(i+1): sngl_vrtx[0],
                                                               "Vertex_{}_Ycoordinate".format(i+1): sngl_vrtx[1],
                                                               "Vertex_{}_Zcoordinate".format(i+1): sngl_vrtx[2]})

    # schedule compact
    idf.newidfobject("SCHEDULE:COMPACT")
    idf.idfobjects["SCHEDULE:COMPACT"][-1].Name = "AHUsch"
    idf.idfobjects["SCHEDULE:COMPACT"][-1].Schedule_Type_Limits_Name = "Fraction"
    idf.idfobjects["SCHEDULE:COMPACT"][-1].Field_1 = "Through: 12/31"
    idf.idfobjects["SCHEDULE:COMPACT"][-1].Field_2 = "For: AllDays"
    idf.idfobjects["SCHEDULE:COMPACT"][-1].Field_3 = "Until: 6:00"
    idf.idfobjects["SCHEDULE:COMPACT"][-1].Field_4 = 0
    idf.idfobjects["SCHEDULE:COMPACT"][-1].Field_5 = "Until: 22:00"
    idf.idfobjects["SCHEDULE:COMPACT"][-1].Field_6 = 1
    idf.idfobjects["SCHEDULE:COMPACT"][-1].Field_7 = "Until: 24:00"
    idf.idfobjects["SCHEDULE:COMPACT"][-1].Field_8 = 0

    # save idf
    idf.save(output_file_name)

input_idf_file = os.path.join("EPlus_files","empty_model.idf")
output_file_name = os.path.join("EPlus_files","updated_model.idf")
model_params = 0  # place holder for parameters
write_idf(input_idf_file, model_params)