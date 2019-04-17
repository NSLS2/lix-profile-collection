from ophyd import Device, Component as Cpt, EpicsMotor, EpicsSignalRO
from ophyd.pseudopos import (pseudo_position_argument, real_position_argument)
from ophyd import (PseudoPositioner, PseudoSingle)
from epics import caget

class XYMotor(Device):
    x = Cpt(EpicsMotor, '-Ax:X}Mtr')
    y = Cpt(EpicsMotor, '-Ax:Y}Mtr')

class XYZMotor(XYMotor):
    z = Cpt(EpicsMotor, '-Ax:Z}Mtr')

class XYPitchMotor(XYMotor):
    pitch = Cpt(EpicsMotor, '-Ax:P}Mtr')

""" note that the piezo slits PVs are incorrectly named X/Y, instead of dX/dY
""" 
class ApertureDev(Device):
    dx = Cpt(EpicsMotor, '-Ax:dX}Mtr')
    dy = Cpt(EpicsMotor, '-Ax:dY}Mtr')
    
class KBMirrorHorizontal(Device):
    x1 = Cpt(EpicsMotor, '-Ax:XU}Mtr')
    x2 = Cpt(EpicsMotor, '-Ax:XD}Mtr')
    y1 = Cpt(EpicsMotor, '-Ax:YU}Mtr')
    y2 = Cpt(EpicsMotor, '-Ax:YD}Mtr')
    pitch_rb = Cpt(EpicsSignalRO, '-Ax:PF_RDBK}Mtr.RBV')

class KBMirrorVertical(Device):
    x = Cpt(EpicsMotor, '-Ax:X}Mtr')
    y1 = Cpt(EpicsMotor, '-Ax:YU}Mtr')
    y2 = Cpt(EpicsMotor, '-Ax:YD}Mtr')
    fine_pitch = Cpt(EpicsMotor, '-Ax:PF}Mtr')
    pitch_rb = Cpt(EpicsSignalRO, '-Ax:PF_RDBK}Mtr.RBV')

class Blades(Device):
    top = Cpt(EpicsMotor, '-Ax:T}Mtr')
    bottom = Cpt(EpicsMotor, '-Ax:B}Mtr')
    outboard = Cpt(EpicsMotor, '-Ax:O}Mtr')
    inboard = Cpt(EpicsMotor, '-Ax:I}Mtr')

class SlitsCenterAndGap(Device):
    x = Cpt(EpicsMotor, '-Ax:X}Mtr')
    dx = Cpt(EpicsMotor, '-Ax:dX}Mtr')
    y = Cpt(EpicsMotor, '-Ax:Y}Mtr')
    dy = Cpt(EpicsMotor, '-Ax:dY}Mtr')

class HRM1(Device):
    y = Cpt(EpicsMotor, '-Ax:Y}Mtr')
    pitch = Cpt(EpicsMotor, '-Ax:Th}Mtr')

class HRM2(Device):
    y = Cpt(EpicsMotor, '-Ax:Y}Mtr')
    pitch = Cpt(EpicsMotor, '-Ax:Th}Mtr')
    # Upstream
    bend1 = Cpt(EpicsMotor, '-Ax:BU}Mtr')
    # Downstream
    bend2 = Cpt(EpicsMotor, '-Ax:BD}Mtr')

class StageScan(Device):
    x = Cpt(EpicsMotor, '-Ax:X}Mtr')
    y = Cpt(EpicsMotor, '-Ax:Y}Mtr')
    r = Cpt(EpicsMotor, '-Ax:Rot}Mtr')
    
class Tilt(Device):
    rx = Cpt(EpicsMotor, '-Ax:RX}Mtr')
    ry = Cpt(EpicsMotor, '-Ax:RY}Mtr')


class Microscope(Device):
    x = Cpt(EpicsMotor, '-Ax:X}Mtr')
    y = Cpt(EpicsMotor, '-Ax:Y}Mtr')
    rx = Cpt(EpicsMotor, '-Ax:Rx}Mtr')
    ry = Cpt(EpicsMotor, '-Ax:Ry}Mtr')
    focus = Cpt(EpicsMotor, '-Ax:F}Mtr')
    polarizer = Cpt(EpicsMotor, '-Ax:Pol}Mtr')
    zoom = Cpt(EpicsMotor, '-Ax:Zm}Mtr')
    
class Screen(Device):
    y=Cpt(EpicsMotor, '-Ax:Y}Mtr')
    
#######################################################
### LIX First Optical Enclosure FOE Optics Hutch A
#######################################################

## White Beam Mirror
wbm = XYPitchMotor('XF:16IDA-OP{Mir:WBM', name='wbm')

## Beam-viewing screen #3
scn3y = EpicsMotor('XF:16IDA-BI{FS:3-Ax:Y}Mtr', name='scn3y')

## Beam-viewing screen #4
scn4y = EpicsMotor('XF:16IDA-BI{FS:4-Ax:Y}Mtr', name='scn4y')

## KB Mirror System
# Horizontal
hfm = KBMirrorHorizontal('XF:16IDA-OP{Mir:KBH', name="hfm")
# Vertical
vfm = KBMirrorVertical('XF:16IDA-OP{Mir:KBV', name='vfm')

## Slits
mps = Blades('XF:16IDA-OP{Slt:1', name='mps')


#######################################################
### LIX Secondary Source Enclosure Hutch B
#######################################################

## Beam Position Monitor
bpm_pos = XYMotor('XF:16IDB-BI{BPM:1', name='bpm_pos')

bpm2_pos = XYMotor('XF:16IDC-BI{BPM:2', name='bpm2')

## Secondary Source Aperture (SSA)
#ssa = ApertureDev('XF:16IDB-OP{Slt:SSA', name='ssa')
ssa1 = ApertureDev('XF:16IDB-OP{Slt:SSA1', name='ssa1')


## Attenuator
# Absorber Set #1
atn1x = EpicsMotor('XF:16IDB-OP{Fltr:Atn-Ax:X1}Mtr', name='atn1x')
# Absorber Set #2
atn2x = EpicsMotor('XF:16IDB-OP{Fltr:Atn-Ax:X2}Mtr', name='atn2x')
# Absorber Set #3
atn3x = EpicsMotor('XF:16IDB-OP{Fltr:Atn-Ax:X3}Mtr', name='atn3x')

## Alternative SSA
#assa = SlitsCenterAndGap('XF:16IDB-OP{Slt:aSSA', name="aSSA")

## Visual Beam Monitor (VBM)
# Focus
#vbm_focus = EpicsMotor('XF:16IDB-BI{FS:VBM-Ax:F}Mtr', name='vbm_focus')
# Zoom
#vbm_zoom = EpicsMotor('XF:16IDB-BI{FS:VBM-Ax:Zm}Mtr', name='vbm_zoom')

#######################################################
### LIX Experimental End Station Enclosure EESE Hutch C
#######################################################

## Harmonic Rejection Mirror HRM1
hrm1 = HRM1('XF:16IDC-OP{Mir:HRM1', name='hrm1')

## Harmonic Rejection Mirror HRM2
hrm2 = HRM2('XF:16IDC-OP{Mir:HRM2', name='hrm2')

## Divergence Defining Aperture (DDA)
dda = SlitsCenterAndGap('XF:16IDC-OP{Slt:DDA', name='dda')

## Beam Position Monitor (BPM)
#bimy = EpicsMotor('XF:16IDC-BI{BPM:2-Ax:Y}Mtr', name='bimy')

## Guard Slits 1
sg1 = SlitsCenterAndGap('XF:16IDC-OP{Slt:G1', name='sg1')

## Guard Slits 2
sg2 = SlitsCenterAndGap('XF:16IDC-OP{Slt:G2', name='sg2')

#########################################
## Detector System
#########################################

## Detector Positioning Stages 
saxs = XYZMotor('XF:16IDC-ES{Stg:SAXS', name='saxs')
waxs1 = XYZMotor('XF:16IDC-ES{Stg:WAXS1', name='waxs1')
waxs2 = XYZMotor('XF:16IDC-ES{Stg:WAXS2', name='waxs2')

## SAXS Beamstop
sbs = XYMotor('XF:16IDC-ES{BS:SAXS', name='sbs')

## screen
screen_SS = Screen('XF:16IDB-BI{SCN:SS',name='screen_ss')
screen_SF = Screen('XF:16IDC-BI{FS:SF',name='screen_sf')

microscope = Microscope('XF:16IDC-ES:InAir{Mscp:1', name='microscope')