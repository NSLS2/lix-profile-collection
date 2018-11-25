from ophyd import (EpicsSignal, Device, Component as Cpt)

# this might not work as intended, uncomment if needed
#import os
#os.environ['EPICS_CA_ADDR_LIST']='10.16.2.59 10.16.2.60 10.16.2.61'

class FastShutter(Device):
    OPEN_SHUTTER = "open"
    CLOSE_SHUTTER = "closed"
    SETTLE_TIME = 0.1  # seconds
    output = Cpt(EpicsSignal,'{shutter:1}sts', string=True, put_complete=True)
    busy = Cpt(EpicsSignal,'{shutter}busy')

    def open(self):
        while True:
            status = self.busy.get()
            if status==0:
                break
            print('shutter busy, re-try opening in 2 seconds ...')
            time.sleep(2)
            
        print("opening shutter ...",)
        #self.output.put(FastShutter.OPEN_SHUTTER)
        self.output.set(FastShutter.OPEN_SHUTTER, settle_time=FastShutter.SETTLE_TIME)
        print(" done.")
        
    def close(self):
        print("closing shutter ...",)
        #self.output.put(FastShutter.CLOSE_SHUTTER)
        self.output.set(FastShutter.CLOSE_SHUTTER, settle_time=FastShutter.SETTLE_TIME)
        print(" done.")


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



def one_nd_step_with_shutter(detectors, step, pos_cache):
    """
    Inner loop of an N-dimensional step scan

    This is the default function for ``per_step`` param`` in ND plans.

    Parameters
    ----------
    detectors : iterable
        devices to read
    step : dict
        mapping motors to positions in this step
    pos_cache : dict
        mapping motors to their last-set positions
    """
    def move():
        yield Msg('checkpoint')
        grp = bp._short_uid('set')
        for motor, pos in step.items():
            if pos == pos_cache[motor]:
                # This step does not move this motor.
                continue
            yield Msg('set', motor, pos, group=grp)
            pos_cache[motor] = pos
        yield Msg('wait', None, group=grp)

    motors = step.keys()
    yield from move()
    yield from bp.abs_set(fast_shutter.output, FastShutter.OPEN_SHUTTER, settle_time=FastShutter.SETTLE_TIME, wait=True)
    yield from trigger_and_read(list(detectors) + list(motors))
    yield from bp.abs_set(fast_shutter.output, FastShutter.CLOSE_SHUTTER, settle_time=FastShutter.SETTLE_TIME, wait=True)
        
        
