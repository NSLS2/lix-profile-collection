from ophyd import EpicsSignal
from bluesky.suspenders import SuspendFloor
from bluesky.suspenders import SuspendCeil
#from bluesky.suspenders import SuspendBoolLow

BEAM_RECOVER_TIME = 30 #Time in seconds
BEAM_THRES = 300
beam_current = EpicsSignal('SR:OPS-BI{DCCT:1}I:Real-I')

beam_current_sus = SuspendFloor(beam_current, BEAM_THRES, sleep=BEAM_RECOVER_TIME)

def install_beam_suspender():
    RE.install_suspender(beam_current_sus)

def uninstall_beam_suspender():
    RE.remove_suspender(beam_current_sus)


bpm_xpos = EpicsSignal('XF:16IDB-CT{Best}:BPM0:PosX_Mean')
BPM_X_THRES_HIGH = 20
BPM_X_THRES_LOW = -20

BPM_RECOVER_TIME=5

bpm_ypos = EpicsSignal('XF:16IDB-CT{Best}:BPM0:PosY_Mean')
BPM_Y_THRES_HIGH = 20
BPM_Y_THRES_LOW = -20

bpm_posx_sus_high = SuspendCeil(bpm_xpos, BPM_X_THRES_HIGH, sleep=BPM_RECOVER_TIME)
bpm_posx_sus_low = SuspendFloor(bpm_xpos, BPM_X_THRES_LOW, sleep=BPM_RECOVER_TIME)

bpm_posy_sus_high = SuspendCeil(bpm_xpos, BPM_Y_THRES_HIGH, sleep=BPM_RECOVER_TIME)
bpm_posy_sus_low = SuspendFloor(bpm_xpos, BPM_Y_THRES_LOW, sleep=BPM_RECOVER_TIME)

#bpm_posx_sus = SuspendFloor(bpm_xpos, BPM_X_THRES, sleep=BPM_RECOVER_TIME)
#bpm_posy_sus = SuspendFloor(bpm_ypos, BPM_Y_THRES, sleep=BPM_RECOVER_TIME)

def install_bpmx_high_suspender():
    RE.install_suspender(bpm_posx_sus_high)

def uninstall_bpmx_high_suspender():
    RE.remove_suspender(bpm_posx_sus_high)
    
def install_bpmx_low_suspender():
    RE.install_suspender(bpm_posx_sus_low)

def uninstall_bpmx_low_suspender():
    RE.remove_suspender(bpm_posx_sus_low)
    
def install_bpmy_high_suspender():
    RE.install_suspender(bpm_posy_sus_high)

def uninstall_bpmy_high_suspender():
    RE.remove_suspender(bpm_posy_sus_high)
    
def install_bpmy_low_suspender():
    RE.install_suspender(bpm_posy_sus_low)

def uninstall_bpmy_low_suspender():
    RE.remove_suspender(bpm_posy_sus_low)
    
#install_bpmx_high_suspender()
#install_bpmx_low_suspender()
#install_bpmy_high_suspender()
#install_bpmy_low_suspender()
#install_beam_suspender()

