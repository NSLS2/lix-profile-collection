from ophyd import (EpicsSignal, Device, Component as Cpt)

import os
os.environ['EPICS_CA_ADDR_LIST']='10.16.2.59 10.16.2.60 10.16.2.61'

class FastShutter(Device):
    OPEN_SHUTTER = "open"
    CLOSE_SHUTTER = "closed"
    SETTLE_TIME = 0.1  # seconds
    output = Cpt(EpicsSignal,'{shutter:1}sts', string=True, put_complete=True)

    def open(self):
        self.output.set(FastShutter.OPEN_SHUTTER, settle_time=FastShutter.SETTLE_TIME)

    def close(self):
        self.output.set(FastShutter.CLOSE_SHUTTER, settle_time=FastShutter.SETTLE_TIME)


fast_shutter = FastShutter('XF:16IDB-BI', name='fast_shutter')


class Scintillator(Device):
    OPEN_SHUTTER = "open"
    CLOSE_SHUTTER = "closed"
    SETTLE_TIME = 0.1  # seconds
    output = Cpt(EpicsSignal,'{shutter:2}sts', string=True, put_complete=True)

    def open(self):
        self.output.set(Scintillator.OPEN_SHUTTER, settle_time=Scintillator.SETTLE_TIME)

    def close(self):
        self.output.set(Scintillator.CLOSE_SHUTTER, settle_time=Scintillator.SETTLE_TIME)


scintillator_shutter = Scintillator('XF:16IDB-BI', name='scintillator_shutter')

class PhotonShutter(Device):
    OPEN_SHUTTER = "Open"
    CLOSE_SHUTTER = "Not Open"
    output = Cpt(EpicsSignal, '{PSh}Pos-Sts', string=True, put_complete=True)
    
    def open(self):
        self.output.set(Scintillator.OPEN_SHUTTER)
        
    def close(self):
        self.output.set(Scintillator.CLOSE_SHUTTER)
            
photon_shutter = PhotonShutter('XF:16IDA-PPS', name='photon_shutter')


class FastShutter2(Device):
    OPEN_SHUTTER = "Force High"
    CLOSE_SHUTTER = "Force Low"
    SETTLE_TIME = 0.1  # seconds
    delay = Cpt(EpicsSignal, '-DlyGen:0}Delay-SP')
    width = Cpt(EpicsSignal, '-DlyGen:0}Width-SP')
    output = Cpt(EpicsSignal,'-Out:FP0}Src:Scale-SP', string=True, put_complete=True)

    
    def open(self):
        self.output.set(FastShutter2.OPEN_SHUTTER, settle_time=FastShutter2.SETTLE_TIME)

    def close(self):
        self.output.set(FastShutter2.CLOSE_SHUTTER, settle_time=FastShutter2.SETTLE_TIME)


fast_shutter2 = FastShutter2('XF:16ID-TS{EVR:C1', name='fast_shutter2')

