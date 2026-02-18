print(f"Loading {__file__}...")

"""
    define type of experiment, and therefore additional startup script to load
    may need to run this to define the motors used in sample_handler_state
    
    the config is defined by the busi command line arguments
    supported configs include:
    
    --sol: solution scattering, must have the S EM in place (sample handler)
    --scan: scanning, must have the M EM in place (scanning with gonio)
    --gen: generic, must have the G EM in place (x-y only)
    --vac: in-vacuum, must have the V EM in place (vacuum chamber with SmarAct positioners)
           disabled for now until a hardware indicator for chamber persence can be established
    --proc: no hardware, data access only
    
"""

import os
BSconfig = os.environ['BS_CONFIG']

EMconfig = EpicsSignal("XF:16IDC-ES:EMconfig")

if BSconfig in ["solution", "scanning", "generic", "vacuum"]:
    # define beamline optics
    reload_macros("components/10-motors.py")        
    reload_macros("components/10-vacuum.py")        
    reload_macros("components/10-zebra.py")
    reload_macros("components/12-shutter.py")
    reload_macros("components/14-energy.py")    
    reload_macros("components/15-transfocator.py")
    reload_macros("components/19-robot.py")
    reload_macros("components/20-ext_trigger.py")
    reload_macros("components/20-bpm.py")
    reload_macros("components/20-detectors.py")
    reload_macros("components/20-pilatus.py")
    reload_macros("components/20-xspress3.py")
    reload_macros("components/20-kinetix.py")
    reload_macros("components/20-bpm.py")
    reload_macros("components/25-XPS.py")
    reload_macros("components/30-decorators.py")
    reload_macros("components/30-traj.py")
    reload_macros("components/31-raster.py")
    reload_macros("components/31-scans.py")

    reload_macros("utils/60-utils.py")
    reload_macros("utils/61-report.py")
    reload_macros("utils/70-blop.py")
    reload_macros("utils/90-settings.py")

    reload_macros("components/21-metadata.py")

    reload_macros("experiments/50-Tctrl.py")

    
if BSconfig=="solution":
    # EM S, run solution startup
    reload_macros("experiments/25-EM_sol.py")
    reload_macros("experiments/25-hplc.py")
    reload_macros("experiments/startup_solution.py")
    ESVacSys = define_vac_system(vacuum_sample_env=False)
elif BSconfig=="scanning":
    # EM M, run scanning startup
    reload_macros("experiments/startup_scanning.py")
    reload_macros("experiments/def-tomo.py")
    ESVacSys = define_vac_system(vacuum_sample_env=False)
elif BSconfig=="generic":
    # EM G, + ss.msy for muscle
    reload_macros("experiments/startup_generic.py")
    ESVacSys = define_vac_system(vacuum_sample_env=False)
elif BSconfig=="vacuum":
    raise Expection("vacuum config current not supported ...")
    reload_macros("experiments/startup_vacscan.py")
    ESVacSys = define_vac_system(vacuum_sample_env=True)
    ESVacSys.acceptablePumpPressure = 0.02

os.chdir(f"/nsls2/data/lix/legacy/{current_cycle}")
