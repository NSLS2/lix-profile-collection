from ophyd import (EpicsSignal, Device, Component as Cpt)


class FastShutter(Device):
    OPEN_SHUTTER = "Force High"
    CLOSE_SHUTTER = "Force Low"
    SETTLE_TIME = 0.1  # seconds
    delay = Cpt(EpicsSignal, '-DlyGen:0}Delay-SP')
    width = Cpt(EpicsSignal, '-DlyGen:0}Width-SP')
    output = Cpt(EpicsSignal,'-Out:FP0}Src:Scale-SP', string=True, put_complete=True)

    
    def open(self):
        self.output.set(FastShutter.OPEN_SHUTTER, settle_time=FastShutter.SETTLE_TIME)

    def close(self):
        self.output.set(FastShutter.CLOSE_SHUTTER, settle_time=FastShutter.SETTLE_TIME)


fast_shutter = FastShutter('XF:16ID-TS{EVR:C1', name='fast_shutter')


