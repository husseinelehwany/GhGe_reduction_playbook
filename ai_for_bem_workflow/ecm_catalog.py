from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum


class Category(str, Enum):
    ENVELOPE  = "envelope"
    HVAC      = "hvac"
    LIGHTING  = "lighting"
    EQUIPMENT = "equipment"
    RENEWABLE = "renewable"


@dataclass
class ECMSpec:
    """Specification for a single Energy Conservation Measure."""
    id: str
    description: str
    instructions: dict
    category: Category
    custom_function: str                 # name of the method in RetrofitsRecommender that applies this ECM

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "instructions": self.instructions,
            "category": self.category.value,
            "custom_function": self.custom_function
        }


class ECMCatalog:
    """
    Registry of available ECMs. The LLM selects ECM IDs from this catalog
    and fills in parameter values; it never writes raw IDF syntax.
    """

    def __init__(self):
        self.ecms: dict[str, ECMSpec] = {}
        self._register_defaults()

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, ecm: ECMSpec):
        """Add or overwrite an ECM in the catalog."""
        self.ecms[ecm.id] = ecm

    def get(self, ecm_id: str) -> ECMSpec:
        """Retrieve an ECM by ID; raises KeyError if not found."""
        return self.ecms[ecm_id]

    def get_ecm_list(self) -> list[dict]:
        """Return all ECMs as a JSON-serializable list of dicts."""
        return [ecm.to_dict() for ecm in self.ecms.values()]


    # ── Built-in catalog ─────────────────────────────────────────────────────

    def _register_defaults(self):

        self.register(ECMSpec(
            id="wall_insulation",
            description="Provide a better R-value for opaque walls.",
            instructions= {"new_objects": "Create a new insulation materials and a construction object named retrofit_wall in the new_object field.",
                           "edit_objects": "",
                           "erase_objects": ""},
            category=Category.ENVELOPE,
            custom_function="apply_wall_insulation",
        ))

        self.register(ECMSpec(
            id="roof_insulation",
            description="Provide a better R-value R-value for the roof insulation.",
            instructions= {"new_objects": "Create a new insulation materials and a construction object retrofit_roof in the new_object field.",
                            "edit_objects": "",
                            "erase_objects": ""},
            category=Category.ENVELOPE,
            custom_function="apply_roof_insulation",
        ))

        self.register(ECMSpec(
            id="window_upgrade",
            description="Replace windows with higher-performance glazing (lower U-value, optimised SHGC).",
            instructions= {"new_objects": "Create a new window material simple glazing system and a window construction named retrofit_window in the new_object field.",
                            "edit_objects": "",
                            "erase_objects": ""},            
            category=Category.ENVELOPE,
            custom_function="apply_window_upgrade"
        ))

        self.register(ECMSpec(
            id="infiltration_reduction",
            description="Reduce air infiltration rate",
            instructions= {"new_objects": "",
                            "edit_objects": "in Zone infiltration design flow rate object set the flow rate per exterior surface area field to a proper value in m3/s.m2",
                            "erase_objects": ""},
            category=Category.ENVELOPE,
            custom_function=None
        ))

        self.register(ECMSpec(
            id="lighting_upgrade",
            description="Replace existing lighting with LED fixtures.",
            instructions= {"new_objects": "",
                            "edit_objects": "in Lights object, set the corrosponding field to the recommended value.",
                            "erase_objects": ""},
            category=Category.LIGHTING,
            custom_function=None
        ))

        self.register(ECMSpec(
            id="lighting_schedule",
            description="Set a night setback for lighting with a suitable after hours fraction.",
            instructions= {"new_objects": "generate an lighting compact schedule named light_schedule.",
                            "edit_objects": "in Lights object, set the schedule to the lighting schedule.",
                            "erase_objects": ""},
            category=Category.LIGHTING,
            custom_function=None
        ))

        self.register(ECMSpec(
            id="setpoints_setback",
            description="Relax the setpoints during unoccupied hours.",
            instructions= {"new_objects": "generate compact setpoints schedules named heating_setpoint_schedule and cooling_setpoint_schedule.",
                            "edit_objects": "in the thermostat object, set the setpoint schedule names to the setpoint schedules.",
                            "erase_objects": ""},
            category=Category.HVAC,
            custom_function=None,
        ))

        self.register(ECMSpec(
            id="economiser_enable",
            description="Enable air-side economiser on AHU. ",
            instructions= {"new_objects": "",
                            "edit_objects": "In the system level HVAC template, set the economiser field to DifferentialDryBulb",
                            "erase_objects": ""},
            category=Category.HVAC,
            custom_function=None
        ))

        self.register(ECMSpec(
            id="heat_recovery",
            description="Add heat recovery to AHU. ",
            instructions= {"new_objects": "",
                            "edit_objects": "In the system level HVAC template, set the heat recovery type to sensible.",
                            "erase_objects": ""},
            category=Category.HVAC,
            custom_function=None
        ))

        self.register(ECMSpec(
            id="DCV",
            description="Add demand controlled ventilation to AHU. ",
            instructions= {"new_objects": "",
                            "edit_objects": "In the system level HVAC template, add the occupancy schedule given in the idf to the minimum outdoor air schedule name.",
                            "erase_objects": ""},
            category=Category.HVAC,
            custom_function=None
        ))

        self.register(ECMSpec(
            id="AHU_schedule",
            description="Add demand controlled ventilation to AHU. ",
            instructions= {"new_objects": "generate an AHU compact schedule.",
                            "edit_objects": "In system level HVAC template, set the system availablity schedule to the AHU schedule.",
                            "erase_objects": ""},
            category=Category.HVAC,
            custom_function= None
        ))

        self.register(ECMSpec(
            id="SAT_reset",
            description="Introduce SAT reset in the AHU.",
            instructions= {"new_objects": "",
                            "edit_objects": "In system level HVAC template, set the Cooling_Coil_Setpoint_Reset_Type field to OutdoorAirTemperatureReset.",
                            "erase_objects": ""},
            category=Category.HVAC,
            custom_function= None
        ))

        # self.register(ECMSpec(
        #     id="electric_coils",
        #     description="Replace gas heating coils with electric ones.",
        #     instructions= {"new_objects": "",
        #                     "edit_objects": "In system level HVAC template, set the heating coil type field to electric, and in the zone level HVAC template set the reheat coils to electric and enable electric baseboard heaters.",
        #                     "erase_objects": ""},
        #     category=Category.HVAC,
        #     custom_function= None
        # ))

        self.register(ECMSpec(
            id="add_heatpump",
            description="Replace the existing HVAC system with a heatpump system. No other HVAC ECMs should be implemented with this measure.",
            instructions= {"new_objects": "generate an AHU compact schedule. Do not add HVAC objects in this field.",
                            "edit_objects": "In system level unitary heatpump AirToAir template, set the system availablity schedule to the AHU schedule.",
                            "erase_objects": "Name existing hvac template objects to be erased later. Do not erase the thermostat object."},
            category=Category.HVAC,
            custom_function= "add_heatpump"
        ))
        
