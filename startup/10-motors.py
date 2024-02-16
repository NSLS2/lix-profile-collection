print(f"Loading {__file__}...")

from ophyd import Device, Component as Cpt, EpicsMotor, EpicsSignalRO
from ophyd.pseudopos import (pseudo_position_argument, real_position_argument)
from ophyd import (PseudoPositioner, PseudoSingle)
from epics import caget
import time

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

class KBMirrorHorizontal(PseudoPositioner):
    x1 = Cpt(EpicsMotor, '-Ax:XU}Mtr')
    x2 = Cpt(EpicsMotor, '-Ax:XD}Mtr')
    y1 = Cpt(EpicsMotor, '-Ax:YU}Mtr')
    y2 = Cpt(EpicsMotor, '-Ax:YD}Mtr')
    pitch_rb = Cpt(EpicsSignalRO, '-Ax:PF_RDBK}Mtr.RBV')
    pitch = Cpt(PseudoSingle, limits=(-15, 15)) # in mrad
    x = Cpt(PseudoSingle)
    Lx = 820 # mm
    
    @pseudo_position_argument
    def forward(self, pos):
        pyd = pos.x + self.Lx*0.001*pos.pitch/2   # mirror is deflecting toward outboard side
        pyu = pos.x - self.Lx*0.001*pos.pitch/2   # pitch>0 ~ upstream x is more negative
        return self.RealPosition(x1=pyu, x2=pud)
        
    @real_position_argument
    def inverse(self, pos):
        px = (pos.x1 + pos.x2)/2
        pp = (pos.x2 - pos.x1)/self.Lx*1000
        return self.PseudoPosition(x=px, pitch=pp)

class KBMirrorVertical(PseudoPositioner):
    x = Cpt(EpicsMotor, '-Ax:X}Mtr')
    y1 = Cpt(EpicsMotor, '-Ax:YU}Mtr')
    y2 = Cpt(EpicsMotor, '-Ax:YD}Mtr')
    #fine_pitch = Cpt(EpicsMotor, '-Ax:PF}Mtr')
    pitch_rb = Cpt(EpicsSignalRO, '-Ax:PF_RDBK}Mtr.RBV')
    pitch = Cpt(PseudoSingle, limits=(-5, 15)) # in mrad
    y = Cpt(PseudoSingle)
    L = 425 # mm
    
    @pseudo_position_argument
    def forward(self, pos):
        pyu = pos.y + L*0.001*pos.pitch/2
        pyd = pos.y - L*0.001*pos.pitch/2
        return self.RealPosition(y1=pyu, y2=pud)
        
    @real_position_argument
    def inverse(self, pos):
        py = (pos.y1 + pos.y2)/2
        pp = (pos.y1 - pos.y2)/self.L*1000
        return self.PseudoPosition(y=py, pitch=pp)
        
    
class Blades(PseudoPositioner):
    """ blade motor positions: >0 is away from the center
    """
    top = Cpt(EpicsMotor, '-Ax:T}Mtr')
    bottom = Cpt(EpicsMotor, '-Ax:B}Mtr')
    outboard = Cpt(EpicsMotor, '-Ax:O}Mtr')
    inboard = Cpt(EpicsMotor, '-Ax:I}Mtr')
    x = Cpt(PseudoSingle, limits=(-5, 5))
    y = Cpt(PseudoSingle, limits=(-5, 5))
    dx = Cpt(PseudoSingle, limits=(-1, 5))
    dy = Cpt(PseudoSingle, limits=(-1, 5))

    @pseudo_position_argument
    def forward(self, pos):
        """pos is a self.PseudoPosition"""
        po = pos.x + pos.dx/2
        pi = -pos.x + pos.dx/2
        pt = pos.y + pos.dy/2
        pb = -pos.y + pos.dy/2
        return self.RealPosition(top=pt, bottom=pb, outboard=po, inboard=pi)

    @real_position_argument
    def inverse(self, pos):
        """pos is self.RealPosition"""
        px = (pos.outboard - pos.inboard)/2
        pdx = pos.outboard + pos.inboard
        py = (pos.top - pos.bottom)/2
        pdy = pos.top + pos.bottom
        return self.PseudoPosition(x=px, dx=pdx, y=py, dy=pdy)
    
    
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
    
class Microscope(PseudoPositioner):
    x = Cpt(EpicsMotor, 'XF:16IDC-ES:InAir{Mscp:1-Ax:X}Mtr')
    y = Cpt(EpicsMotor, 'XF:16IDC-ES:InAir{Mscp:1-Ax:Y}Mtr')
    kz1 = Cpt(EpicsMotor, 'XF:16IDC-ES:InAir{Mscp:1-Ax:kz1}Mtr')
    kz2 = Cpt(EpicsMotor, 'XF:16IDC-ES:InAir{Mscp:1-Ax:kz2}Mtr')
    Rx = Cpt(PseudoSingle, limits=(-5, 5))
    Ry = Cpt(PseudoSingle, limits=(-5, 5))
    # this is the distance between the two pushers
    Lx = 100
    # this is the distance between the pushers and the 3rd support
    Ly = 165
    #focus = Cpt(EpicsMotor, '-Ax:F}Mtr')
    #polarizer = Cpt(EpicsMotor, '-Ax:Pol}Mtr')
    #zoom = Cpt(EpicsMotor, '-Ax:Zm}Mtr')
    
    @pseudo_position_argument
    def forward(self, pos):
        """pos is a self.PseudoPosition"""
        ps = np.radians(pos.Rx)*self.Ly*2
        pd = np.radians(pos.Ry)*self.Lx
        return self.RealPosition(kz1 = (ps+pd)/2, kz2 = (ps-pd)/2, x=self.x.position, y=self.y.position)

    @real_position_argument
    def inverse(self, pos):
        """pos is self.RealPosition"""
        pRy = np.degrees((pos.kz1 - pos.kz2)/self.Lx)
        pRx = np.degrees(0.5*(pos.kz1 + pos.kz2)/self.Ly)
        return self.PseudoPosition(Rx=pRx, Ry=pRy)

    
#######################################################
### LIX First Optical Enclosure FOE Optics Hutch A
#######################################################

## White Beam Mirror
wbm = XYPitchMotor('XF:16IDA-OP{Mir:WBM', name='wbm')

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
ssa = Blades('XF:16IDB-OP{Slt:SSA1', name="ssa")


## Attenuator
# Absorber Set #1
atn1x = EpicsMotor('XF:16IDB-OP{Fltr:Attn-Ax:X1}Mtr', name='atn1x')
# Absorber Set #2
atn2x = EpicsMotor('XF:16IDB-OP{Fltr:Attn-Ax:X2}Mtr', name='atn2x')
# Absorber Set #3
atn3x = EpicsMotor('XF:16IDB-OP{Fltr:Attn-Ax:X3}Mtr', name='atn3x')


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
sg2 = Blades('XF:16IDC-OP{Slt:G2', name='sg2')
sg2.inboard.user_offset_dir.put(1)
sg2.outboard.user_offset_dir.put(1)
sg2.top.user_offset_dir.put(0)
sg2.bottom.user_offset_dir.put(1)

#########################################
## Detector System
#########################################

## Detector Positioning Stages 
saxs = XYZMotor('XF:16IDC-ES{Stg:SAXS', name='saxs')
waxs1 = XYZMotor('XF:16IDC-ES{Stg:WAXS1', name='waxs1')
waxs2 = XYZMotor('XF:16IDC-ES{Stg:WAXS2', name='waxs2')

## SAXS Beamstop
sbs = XYMotor('XF:16IDC-ES{BS:SAXS', name='sbs')

microscope = Microscope(name='microscope', concurrent=True)

def home_motor(mot, forward=True, ref_position=0, travel_range=-1, safety=0.2):
    """ this function homes a motor without EPICS support; must have hard limits
    
        move mot in the specified direction (forward by default) until the motor hit the hard limit (must be present)
        will adjust/remove soft limits to permit motion
        set the position at the hard limit to ref_position
        and return the the starting position once the limit is found
        the soft limit will be reset to a safety distance from the hard limit
        the soft limit on the othe end will be reset based on the travel_range, if given
    """
    if not isinstance(mot, EpicsMotor):
        print(f"{mot} is not a EpicsMotor.")
        return

    print(f"Warning: running this function will move {mot.name} indefinity, hard limit must be present.")
    response = input("OK to preceed (n/Y)?")
    if response!="Y":
        print("Aborted.")

    pos0 = mot.position
    pos1 = pos0
    step = (100 if forward else -100)

    try:
        while True:
            pos1 += step
            if step>0 and pos1>mot.limits[1]:
                mot.set_lim(low=mot.limits[0], high=pos1+safety)
            if step<0 and pos1<mot.limits[0]:
                mot.set_lim(low=pos1-safety, high=mot.limits[1])
            RE(mov(mot, pos1))
    except Exception as e:
        print(f"motion aborted, exception: {e}")

    disp = pos0-mot.position
    msg = f"setting {mot.name} position from {mot.position} to {ref_position}"
    print(msg)
    write_log_msg(msg)
    mot.set_current_position(ref_position)

    time.sleep(1)  # not sure why this is necessary, but otherwise things break
    RE(mov(mot, disp+ref_position))
    ll,hl = mot.limits
    if forward:
        hl = ref_position-safety
        if travel_range>0:
            ll = ref_position-travel_range+safety
    else:
        ll = ref_position+safety
        if travel_range>0:
            hl = ref_position+travel_range-safety
    mot.set_lim(ll,hl)

def ready_for_robot(motors, positions, init=False):
    #print(motors, positions)
    def cb(*args, obj, sub_type, **kwargs):
        print(f"clearing motor motion watch, triggered by {obj.name}")
        ready_for_robot.EMready.set(0).wait()
        for mot in ready_for_robot.motors:
            #mot.clear_sub(cb)
            mot.unsubscribe(ready_for_robot.subid[mot.name])
            del ready_for_robot.subid[mot.name]
        ready_for_robot.motors = []

    if init:
        ready_for_robot.motors = []    
        ready_for_robot.subid = {}
        ready_for_robot.EMready = EpicsSignal("XF:16IDC-ES:EMready")
        ready_for_robot.EMready.set(0).wait()
        return
    
    print("setting up motor motion watch ...")
    for mot,pos in zip(motors, positions):
        mot.move(pos).wait()
        time.sleep(0.5)
        ready_for_robot.subid[mot.name] = mot.subscribe(cb, event_type='start_moving')   # any time the motor moves
    ready_for_robot.motors = motors
    ready_for_robot.EMready.set(1).wait()
