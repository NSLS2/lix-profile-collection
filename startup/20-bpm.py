from ophyd import Device, EpicsSignal, Component as Cpt


class Best(Device):
    x_mean  = Cpt(EpicsSignal, 'PosX_Mean')
    x_std = Cpt(EpicsSignal, 'PosX_Std')
    y_mean  = Cpt(EpicsSignal, 'PosY_Mean')
    y_std = Cpt(EpicsSignal, 'PosY_Std')
    int_mean  = Cpt(EpicsSignal, 'Int_Mean')
    int_std = Cpt(EpicsSignal, 'Int_Std')

best = Best('XF:16IDB-CT{Best}:BPM0:', name='best')
