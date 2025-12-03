print(f"Loading {__file__}...")

"""
We use SOFT_IN:B0 on the Zebra box to produce the external trigger signal for detectors in step 
scans. Since we do not know which detectors will be used, ideally a separate Ophyd device should 
implment the trigger() function to produce this electrical signal. This device would also need 
to be used as a detector in scans, even if it does not produce any data. The time stamps could 
be useful though.

This device should not be included in fly scans.

The trigger signals should be produced at intervals no shorter than the specified delay
In a step scan, this could be limited by motor motion or other detectors
But the delay could be used to limit how fast detectors produce data

thread

"""

from ophyd.device import Device
import threading,time

class ExtTrigger(Device):
    def __init__(self, name, *args, **kwargs):
        super().__init__(name=name, **kwargs)
        self.delay = 0.01
        self.trigger_lock = threading.Lock()
        self._status = None
        self._trigger_signal = EpicsSignal('XF:16IDC-ES{Zeb:1}:SOFT_IN:B0')   
        self.data_key = "ext_trigger"
        self.timestamp = time.time()

    def set_delay(self, delay):
        self.delay = delay
    
    def repeat_ext_trigger(self, rep):
        """ this is used to produce external triggers to complete data collection by camserver
        """
        for i in reversed(range(rep)):
            self._trigger_signal.put(1, wait=True)
            self._trigger_signal.put(0, wait=True)
            time.sleep(self.delay)
            print(f"# of triggers to go: {i} \r", end="")

    def describe(self):
        return {self.name: {"source": "None",
                            "dtype": "number",
                            "shape": [],
                            "precision": 1}}
        
    def read(self):
        return {self.name: {"value": 0., "timestamp": self.timestamp}}
    
    def trigger(self):
        print("ext trigger ...")
        self._status = DeviceStatus(device=self)
        while self.trigger_lock.locked():
            time.sleep(self.delay)
        self.timestamp = time.time()
        self._trigger_signal.put(1, wait=True)
        self._trigger_signal.put(0, wait=True)
        threading.Timer(self.delay, self._status._finished, ()).start()

        return self._status

ext_trig = ExtTrigger("TTLtrigger")

def set_exp_time(dets, exp):
    for det in dets:
        if hasattr(det, 'exp_time'):
            det.exp_time(exp)
    ext_trig.set_delay(exp+0.05)   

def set_num_images(dets, n_triggers, img_per_trig=1):
    for det in dets:
        if hasattr(det, 'set_num_images'):
            det.set_num_images(n_triggers, img_per_trig)

