from ophyd import Device, EpicsSignal, Component as Cpt
from ophyd import QuadEM

class Best(Device):
    x_mean  = Cpt(EpicsSignal, ':BPM0:PosX_Mean')
    x_std = Cpt(EpicsSignal, ':BPM0:PosX_Std')
    y_mean  = Cpt(EpicsSignal,':BPM0:PosY_Mean')
    y_std = Cpt(EpicsSignal, ':BPM0:PosY_Std')
    int_mean  = Cpt(EpicsSignal, ':BPM0:Int_Mean')
    int_std = Cpt(EpicsSignal, ':BPM0:Int_Std')
    ch1 = Cpt(EpicsSignal, ':TetrAMM0:Ch1')
    ch2 = Cpt(EpicsSignal, ':TetrAMM0:Ch2')
    ch3 = Cpt(EpicsSignal, ':TetrAMM0:Ch3')
    ch4 = Cpt(EpicsSignal, ':TetrAMM0:Ch4')

best = Best('XF:16IDB-CT{Best}',name='best')

em1 = QuadEM('XF:16IDC-ES{NSLS_EM:1}', name='em1')
em2 = QuadEM('XF:16IDC-ES{NSLS_EM:2}', name='em2')

