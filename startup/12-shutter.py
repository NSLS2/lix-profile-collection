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

class PhotonShutter(Device):
    OPEN_SHUTTER = "Open"
    CLOSE_SHUTTER = "Not Open"
    output = Cpt(EpicsSignal, '{PSh}Pos-Sts', string=True, put_complete=True)
    
    def open(self):
        self.output.set(Scintillator.OPEN_SHUTTER)
        
    def close(self):
        self.output.set(Scintillator.CLOSE_SHUTTER)
          
fast_shutter = FastShutter('XF:16IDB-BI', name='fast_shutter')
photon_shutter = PhotonShutter('XF:16IDA-PPS', name='photon_shutter')
