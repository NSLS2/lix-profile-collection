from ophyd import Device, EpicsSignal, Signal, Component as Cpt
from ophyd.areadetector import (ADComponent as ADCpt, StatsPlugin)
from ophyd.quadem import NSLS_EM, TetrAMM, QuadEM
from ophyd import DeviceStatus
import numpy as np

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


class TetrAMM(QuadEM):
    port_name = Cpt(Signal, value='TetrAMM')

class NSLS_EM1(NSLS_EM):
    _default_read_attrs = []
    _default_configuration_attrs = []
 

best = Best('XF:16IDB-CT{Best}',name='best')

#em1 = NSLS_EM1('XF:16IDC-ES{NSLS_EM:1}', name='em1')
#em1.read_attrs = ['current1', 'current2', 'current3', 'current4', 'sum_all']
#em1.sum_all.mean_value.kind = 'hinted'

em2 = NSLS_EM1('XF:16IDC-ES{NSLS_EM:2}', name='em2')
em2.read_attrs = ['current1', 'current2', 'current3', 'current4', 'sum_all']
em2.sum_all.mean_value.kind = 'hinted'

#tetramm = TetrAMM('XF:16IDC-ES{TETRAMM:1}', name='tetramm')
