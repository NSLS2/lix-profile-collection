from ophyd.signal import (EpicsSignal, EpicsSignalRO)
from ophyd.utils.epics_pvs import (raise_if_disconnected, AlarmSeverity)
from ophyd.device import (Device, Component as Cpt)
from ophyd.status import wait as status_wait

import bluesky.plans as bp
import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp

class EpicsGapMotor(EpicsMotor):
    # user the normal user_setpoint signal, but must turn off/on the brake before/after motion
    user_setpoint = Cpt(EpicsSignal, '.VAL', limits=True)
    # alternatively, use this signal and the controller will do it; 
    #    sometimes gets stuck during scan testing, click Go in CSS then resumes
    #user_setpoint = Cpt(EpicsSignal, '-SP-Go', limits=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)        


IVUgap = EpicsGapMotor("SR:C16-ID:G1{IVU:1-Ax:Gap}-Mtr", name='IVUgap')
IVUgapBrake = EpicsSignal("SR:C16-ID:G1{IVU:1}BrakesDisengaged-Sts", write_pv="SR:C16-ID:G1{IVU:1}BrakesDisengaged-SP")

def IVU_brake_wrapper(plan):
    plan = bpp.pchain(bps.abs_set(IVUgapBrake, 1, wait=True), plan)
    plan = bpp.finalize_wrapper(plan, bps.abs_set(IVUgapBrake, 0, wait=True))
    return (yield from plan)

IVU_brake_decorator = bpp.make_decorator(IVU_brake_wrapper)

mov_gap = IVU_brake_decorator()(bps.mv)
gap_dscan = IVU_brake_decorator()(dscan)
gap_ascan = IVU_brake_decorator()(ascan)

# unit of the gap value is microns
# 
# examples:
# 
#    RE(gap_ascan([det], IVUgap, 5800, 6200, 101))
#
#    RE(gap_dscan([det], IVUgap, -500, 500, 51))
#
#    RE(mov_gap(IVUgap, 15000))
#
