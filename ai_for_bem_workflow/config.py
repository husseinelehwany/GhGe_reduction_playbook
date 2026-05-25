import os
import sys

if sys.platform == "win32":
    EPLUS_DIR = r"C:\EnergyPlusV24-1-0"
else:
    EPLUS_DIR = "/usr/local/EnergyPlus-24-1-0"

EPLUS_IDD = os.path.join(EPLUS_DIR, "Energy+.idd")
