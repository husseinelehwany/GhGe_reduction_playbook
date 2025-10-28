import numpy as np
import pandas as pd
import os
from eppy import modeleditor
from eppy.modeleditor import IDF

# Path to the EnergyPlus .idd file
idd_file = "C:\EnergyPlusV24-1-0\Energy+.idd"
dir_path = r"C:\Users\Hussein Elehwany\Desktop\OneDrive backup\PostDoc\GHGe Playbook\DOE Prototype Building Models"
folder_name = r"InternationalFalls_2022_v241"
idf_file = "ASHRAE901_OfficeSmall_STD2022_InternationalFalls.idf"

# Set up the IDF class to use the IDD file and Read the IDF file
# IDF.setiddname(idd_file)
# my_idf = IDF(os.path.join(dir_path, folder_name, idf_file))

class Building:
    def __init__(self, idd_file, idf_file):
        IDF.setiddname(idd_file)
        self.idf = IDF(idf_file)
        self.envelope_comps = []

    def add_envelope_comp(self, construction_obj, boundary_condition, type):
        self.envelope_comps.append(EnvelopeComponent(construction_obj, boundary_condition, type))
        # find all materials in this envelope component
        self.envelope_comps[-1].get_layer_names(self.idf)
        self.envelope_comps[-1].calc_Rvalue()

    def find_envelope_surface(self, type, boundary_condition):
        unique_constructions = []
        for surface in self.idf.idfobjects["BUILDINGSURFACE:DETAILED"]:
            if (surface.Surface_Type == type) and (surface.Outside_Boundary_Condition == boundary_condition):
                # do not repeat constructions
                if surface.Construction_Name not in unique_constructions:
                    unique_constructions.append(surface.Construction_Name)
                    # find the idf construction object
                    exterior_const = [x for x in self.idf.idfobjects["CONSTRUCTION"] if x.Name == surface.Construction_Name]
                    if len(exterior_const) > 1:
                        print(f"Warning, multiple constructions with the name {surface.Construction_Name} found")
                    self.add_envelope_comp(exterior_const[0], "external", type)


    def print_Rvalue_envelope(self):
        results = []
        for component in self.envelope_comps:
            results.append({"Name":  component.name, "R_value": component.r_value})
        return results


class EnvelopeComponent:
    """
    an object for a single EnvelopeComponent or construction
    """
    def __init__(self, eppy_construction, boundary_condition, type):
        self.eppy_construction = eppy_construction
        self.name = eppy_construction.Name
        self.boundary_condition = boundary_condition
        self.type = type
        self.layers = []
        self.r_value = 0

    def get_layer_names(self, idf):
        for layer in self.eppy_construction.fieldnames[1:]:  # skip the Name field
            if "Layer" in layer: # as in Outside Layer, Layer 2 ...
                material_name = getattr(self.eppy_construction, layer)
                if material_name:  # if the field is not empty
                    # find the layer in "MATERIAL"
                    material_obj = [x for x in idf.idfobjects["MATERIAL"] if x.Name == material_name]
                    if len(material_obj) > 0:
                        tmp_resistance = Resistance(material_obj[0], "MATERIAL")
                        self.layers.append(tmp_resistance)
                    # find the layer in "MATERIAL:NOMASS"
                    material_obj = [x for x in idf.idfobjects["MATERIAL:NOMASS"] if x.Name == material_name]
                    if len(material_obj) > 0:
                        tmp_resistance = Resistance(material_obj[0], "MATERIAL:NOMASS")
                        self.layers.append(tmp_resistance)

    def calc_Rvalue(self):
        for resistance in self.layers:
            self.r_value += resistance.r_value
        return self.r_value


class Resistance:
    """
    an object for a single layer or a thermal resistance
    """
    def __init__(self, eppy_material, type):
        self.eppy_material = eppy_material
        self.name = eppy_material.Name
        self.type = type  # "MATERIAL" or "MATERIAL:NOMASS"
        self.r_value = self.get_Rvalue()

    def get_Rvalue(self):
        if self.type == "MATERIAL":
            thickness = float(self.eppy_material.Thickness)  # in meters
            conductivity = float(self.eppy_material.Conductivity)  # W/m-K
            self.r_value = thickness / conductivity
        elif self.type == "MATERIAL:NOMASS":
            self.r_value = float(self.eppy_material.Thermal_Resistance)
        return self.r_value

small_office = Building(idd_file, os.path.join(dir_path, folder_name, idf_file))
small_office.find_envelope_surface("Wall", "Outdoors")
print(small_office.print_Rvalue_envelope())






