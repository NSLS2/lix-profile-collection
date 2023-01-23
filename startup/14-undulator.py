from ophyd.signal import (EpicsSignal, EpicsSignalRO)
from ophyd.utils.epics_pvs import (raise_if_disconnected, AlarmSeverity)
from ophyd.device import (Device, Component as Cpt)
from ophyd.status import wait as status_wait


"""
   The gap motor brake is re-engaged automatically after a pre-defined time period after it is 
   released. The length of this time period can be accessed through SR:C16-ID:G1{IVU:1}BrakeTimeout-SP 
   
   The following is adapted from DAMA implementation. 
   
   Alternatively, use profile_collection/startup/32-undulator-2019Jan.py 
   
"""

from ophyd import EpicsMotor
from ophyd.signal import (EpicsSignal, EpicsSignalRO)
from ophyd.utils.epics_pvs import (raise_if_disconnected, AlarmSeverity)
from ophyd.device import (Device, Component as Cpt)
from ophyd.status import wait as status_wait

import bluesky.plans as bp
import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp

class EpicsGapMotor(EpicsMotor):

    def __init__(self, brakeDevice, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.brake = brakeDevice
        
    def move(self, *args, **kwargs):
        if self.brake.get()==0:
            self.brake.set(1).wait()
        return super().move(*args, **kwargs)

IVUgapBrake = EpicsSignal("SR:C16-ID:G1{IVU:1}BrakesDisengaged-Sts", write_pv="SR:C16-ID:G1{IVU:1}BrakesDisengaged-SP")
IVUgap = EpicsGapMotor(IVUgapBrake, "SR:C16-ID:G1{IVU:1-Ax:Gap}-Mtr", name='IVUgap')
