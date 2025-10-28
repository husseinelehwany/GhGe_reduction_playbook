import numpy as np
import pandas as pd
from eppy import modeleditor
from eppy.modeleditor import IDF
import os

def write_idf(input_idf_file, model_params,output_file_name):
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
        idf.newidfobject("MATERIAL")
        idf.idfobjects["MATERIAL"][-1].Name = row["Name"]
        idf.idfobjects["MATERIAL"][-1].Roughness = row["Roughness"]
        idf.idfobjects["MATERIAL"][-1].Thickness = row["Thickness"]/1000
        idf.idfobjects["MATERIAL"][-1].Conductivity = row["Conductivity"]
        idf.idfobjects["MATERIAL"][-1].Density = row["Density"]
        idf.idfobjects["MATERIAL"][-1].Specific_Heat = row["Specific_Heat"]

    # Construction
    if model_params["envelope"] == "good":
        insulation_mat = "good_insulation"
    elif model_params["envelope"] == "average":
        insulation_mat = "average_insulation"
    elif model_params["envelope"] == "poor":
        insulation_mat = "poor_insulation"
    idf.newidfobject("CONSTRUCTION")
    idf.idfobjects["CONSTRUCTION"][-1].Name = "Exterior Wall"
    idf.idfobjects["CONSTRUCTION"][-1].Outside_Layer = insulation_mat

    idf.newidfobject("CONSTRUCTION")
    idf.idfobjects["CONSTRUCTION"][-1].Name = "Exterior Floor"
    idf.idfobjects["CONSTRUCTION"][-1].Outside_Layer = "Cast concrete"
    idf.idfobjects["CONSTRUCTION"][-1].Layer_2 = insulation_mat

    idf.newidfobject("CONSTRUCTION")
    idf.idfobjects["CONSTRUCTION"][-1].Name = "Exterior Roof"
    idf.idfobjects["CONSTRUCTION"][-1].Outside_Layer = "Cast concrete"
    idf.idfobjects["CONSTRUCTION"][-1].Layer_2 = insulation_mat

    idf.newidfobject("CONSTRUCTION")
    idf.idfobjects["CONSTRUCTION"][-1].Name = "Exterior Window"
    idf.idfobjects["CONSTRUCTION"][-1].Outside_Layer = "simple_glass"

    ## Building surface detail
    bldg_layout = model_params["layout"]
    for i in range(len(bldg_layout.surfaces)):
        new_coordinates = bldg_layout.surfaces[i].vertices
        idf.newidfobject("BUILDINGSURFACE:DETAILED")
        idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Name = bldg_layout.surfaces[i].name
        idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Surface_Type = bldg_layout.surfaces[i].surface_type
        if bldg_layout.surfaces[i].surface_type == "Wall":
            idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Construction_Name = "Exterior Wall"
        elif bldg_layout.surfaces[i].surface_type == "Floor":
            idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Construction_Name = "Exterior Floor"
        elif bldg_layout.surfaces[i].surface_type == "Roof":
            idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Construction_Name = "Exterior Roof"

        idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Zone_Name = "zone1"
        idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Space_Name = ""
        idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Outside_Boundary_Condition = "Outdoors"
        idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Outside_Boundary_Condition_Object = ""
        idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Sun_Exposure = "SunExposed"
        idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Wind_Exposure = "WindExposed"
        idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].View_Factor_to_Ground = ""
        idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].Number_of_Vertices = len(new_coordinates)

        for i in range(len(new_coordinates)):
            sngl_vrtx = new_coordinates[i]
            idf.idfobjects["BUILDINGSURFACE:DETAILED"][-1].update({"Vertex_{}_Xcoordinate".format(i+1): sngl_vrtx[0],
                                                                   "Vertex_{}_Ycoordinate".format(i+1): sngl_vrtx[1],
                                                                   "Vertex_{}_Zcoordinate".format(i+1): sngl_vrtx[2]})

    # Windows
    for i in range(len(bldg_layout.surfaces)):
        if bldg_layout.surfaces[i].surface_type == "Wall":
            x_start, y_start, window_length, window_height = bldg_layout.surfaces[i].get_window_dims(model_params["WWR"])
            idf.newidfobject("WINDOW")
            idf.idfobjects["WINDOW"][-1].Name = "Window_{}".format(bldg_layout.surfaces[i].name)
            idf.idfobjects["WINDOW"][-1].Construction_Name = "Exterior Window"
            idf.idfobjects["WINDOW"][-1].Building_Surface_Name = bldg_layout.surfaces[i].name
            idf.idfobjects["WINDOW"][-1].Starting_X_Coordinate = x_start
            idf.idfobjects["WINDOW"][-1].Starting_Z_Coordinate = y_start
            idf.idfobjects["WINDOW"][-1].Length = window_length
            idf.idfobjects["WINDOW"][-1].Height = window_height


    # Infiltration
    idf.newidfobject("ZONEINFILTRATION:DESIGNFLOWRATE")
    idf.idfobjects["ZONEINFILTRATION:DESIGNFLOWRATE"][-1].Name = "infiltration"
    idf.idfobjects["ZONEINFILTRATION:DESIGNFLOWRATE"][-1].Zone_or_ZoneList_Name = "zone1"
    idf.idfobjects["ZONEINFILTRATION:DESIGNFLOWRATE"][-1].Design_Flow_Rate_Calculation_Method = "Flow/Zone"
    if model_params["envelope"] == "good":
        idf.idfobjects["ZONEINFILTRATION:DESIGNFLOWRATE"][-1].Design_Flow_Rate = 0.00015
    elif model_params["envelope"] == "average":
        idf.idfobjects["ZONEINFILTRATION:DESIGNFLOWRATE"][-1].Design_Flow_Rate = 0.00025
    elif model_params["envelope"] == "poor":
        idf.idfobjects["ZONEINFILTRATION:DESIGNFLOWRATE"][-1].Design_Flow_Rate = 0.00035

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

    # people
    idf.newidfobject("PEOPLE")
    idf.idfobjects["PEOPLE"][-1].Name = "people"
    idf.idfobjects["PEOPLE"][-1].Zone_or_ZoneList_or_Space_or_SpaceList_Name = "zone1"
    idf.idfobjects["PEOPLE"][-1].Number_of_People_Schedule_Name = "Always On"
    idf.idfobjects["PEOPLE"][-1].Number_of_People_Calculation_Method = "People"
    idf.idfobjects["PEOPLE"][-1].Number_of_People = model_params["people"]
    idf.idfobjects["PEOPLE"][-1].Activity_Level_Schedule_Name = "Office Activity Schedule"
    idf.idfobjects["PEOPLE"][-1].Mean_Radiant_Temperature_Calculation_Type = "EnclosureAveraged"


    # equipment intensity 7.5W/m 2 . For lights, it used to be around 8.5W/m2 but with efficient led lights it is around 3.5-4 W/m2.

    # save idf
    idf.save(output_file_name)

