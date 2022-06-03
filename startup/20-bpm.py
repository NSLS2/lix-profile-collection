from ophyd import Device, EpicsSignal, Signal, EpicsSignalWithRBV, Component as Cpt
from ophyd.areadetector import (ADComponent as ADCpt, StatsPlugin)
from ophyd.quadem import NSLS_EM,TetrAMM,QuadEM,QuadEMPort
from ophyd import DeviceStatus
import numpy as np

from ophyd import DynamicDeviceComponent as DDCpt
from collections import OrderedDict
from nslsii.ad33 import QuadEMV33

class Best(Device):
    x_mean  = Cpt(EpicsSignal, ':BPM0:PosX_Mean')
    posx = Cpt(EpicsSignal, ':BPM0:PosX')
    x_std = Cpt(EpicsSignal, ':BPM0:PosX_Std')
    y_mean  = Cpt(EpicsSignal,':BPM0:PosY_Mean')
    posy  = Cpt(EpicsSignal,':BPM0:PosY')
    y_std = Cpt(EpicsSignal, ':BPM0:PosY_Std')
    int_mean  = Cpt(EpicsSignal, ':BPM0:Int_Mean')
    int_std = Cpt(EpicsSignal, ':BPM0:Int_Std')
    ch1 = Cpt(EpicsSignal, ':TetrAMM0:Ch1')
    ch2 = Cpt(EpicsSignal, ':TetrAMM0:Ch2')
    ch3 = Cpt(EpicsSignal, ':TetrAMM0:Ch3')
    ch4 = Cpt(EpicsSignal, ':TetrAMM0:Ch4')
    acquire_time = Cpt(Signal, name='time', value=1)

    def trigger(self):
        #TODO: modify settle_time to be from a acquiretime pv
        acq_time = self.acquire_time.get()
        _status = DeviceStatus(self, settle_time=acq_time)
        _status._finished(success=True)
        return _status

### QuadEM def adapted from XFP

class TimeSeries(Device):
    SumAll = ADCpt(EpicsSignalRO, "SumAll:TimeSeries", kind='normal')
    current1 = ADCpt(EpicsSignalRO, "Current1:TimeSeries", kind='normal')
    current2 = ADCpt(EpicsSignalRO, "Current2:TimeSeries", kind='normal')
    current3 = ADCpt(EpicsSignalRO, "Current3:TimeSeries", kind='normal')
    current4 = ADCpt(EpicsSignalRO, "Current4:TimeSeries", kind='normal')

    acquire = ADCpt(EpicsSignal, "TSAcquire", kind='omitted')
    acquire_mode = ADCpt(EpicsSignal, "TSAcquireMode", string=True, kind='config')
    acquiring = ADCpt(EpicsSignalRO, "TSAcquiring", kind='omitted')

    time_axis = ADCpt(EpicsSignalRO, "TSTimeAxis", kind='config')
    read_rate = ADCpt(EpicsSignal, "TSRead.SCAN", string=True, kind='config')
    num_points = ADCpt(EpicsSignal, "TSNumPoints", kind='config')
    averaging_time = ADCpt(EpicsSignalWithRBV, "TSAveragingTime", kind="config")
    current_point = ADCpt(EpicsSignalRO, "TSCurrentPoint", kind="omitted")


class LiX_EM(QuadEM):
    ts = ADCpt(TimeSeries, "TS:")
    x_position = ADCpt(EpicsSignalRO, "PosX:MeanValue_RBV", kind='normal')
    y_position = ADCpt(EpicsSignalRO, "PosY:MeanValue_RBV", kind='normal')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update([(self.acquire_mode, "Single")])  # single mode
        self.configuration_attrs = [
            "integration_time",
            "averaging_time",
            "em_range",
            "num_averaged",
            "values_per_read",
        ]


"""
class TetrAMM(QuadEM):
    port_name = Cpt(Signal, value='TetrAMM')

class NSLS_EM1(NSLS_EM):
    _default_read_attrs = []
    _default_configuration_attrs = []
 
"""

em1 = LiX_EM('XF:16IDC-ES{NSLS_EM:1}', name='em1')
em1.read_attrs = ['current1', 'current2', 'current3', 'current4', 'sum_all']
em1.sum_all.mean_value.kind = 'hinted'

em2 = LiX_EM('XF:16IDC-ES{NSLS_EM:2}', name='em2')
em2.read_attrs = ['current1', 'current2', 'current3', 'current4', 'sum_all']
em2.sum_all.mean_value.kind = 'hinted'

em0 = LiX_EM('XF:16IDA{NSLS_EM:3}', name='em0')
em0.read_attrs = ['x_position', 'y_position']

#tetramm = TetrAMM('XF:16IDC-ES{TETRAMM:1}', name='tetramm')
bpm = Best('XF:16IDB-CT{Best}', name='bpm')

