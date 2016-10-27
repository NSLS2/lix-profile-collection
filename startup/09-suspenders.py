from ophyd import EpicsSignal
from bluesky.suspenders import SuspendFloor

BEAM_RECOVER_TIME = 30 #Time in seconds
BEAM_THRES = 200
beam_current = EpicsSignal('SR:OPS-BI{DCCT:1}I:Real-I')

beam_current_sus = SuspendFloor(beam_current, BEAM_THRES, sleep=BEAM_RECOVER_TIME)


def install_beam_suspender():
    RE.install_suspender(beam_current_sus)

def uninstall_beam_suspender():
    RE.remove_suspender(beam_current_sus)

#install_beam_suspender()

