# This script reads input for the survey
# and generates data in a transferable form to create the idf file
import numpy as np

# Geometry
class Surface:
    def __init__(self, name: str, coordinates: np.ndarray):
        self.name = name
        self.coordinates = coordinates  # Expected shape: (n_vertices, 3)


class Layout:
    def __init__(self, layout_name: str,dimensions: np.ndarray):
        self.layout_name = layout_name
        self.dimensions = dimensions
        self.layout_coordinates = self.get_layout_coordinates()
        self.surfaces = self.get_surfaces_coordinates()

    def get_layout_coordinates(self):
        # return vertices of selected layout
        pass

    def get_surfaces_coordinates(self):
        # return vertices of surfaces of a layout
        pass



# envelope

# Internal loads

# HVAC

# output csv or xml


def read_ghge_survey(survey_file):
    rect_layout = Layout("rectangle",[2, 3, 4])


read_ghge_survey("Survey file")