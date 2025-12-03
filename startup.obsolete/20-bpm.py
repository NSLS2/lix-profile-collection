print(f"Loading {__file__}...")

from ophyd import Device, EpicsSignal, Signal, EpicsSignalWithRBV, Component as Cpt
from ophyd.areadetector import (ADComponent as ADCpt, StatsPlugin)
from ophyd.quadem import NSLS_EM,TetrAMM,QuadEM,QuadEMPort
from ophyd import DeviceStatus
import numpy as np
from ophyd.sim import NullStatus
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

class LiXTetrAMM(QuadEM):
    conf = Cpt(QuadEMPort, port_name="TetrAMM", kind="omitted")
    ts = ADCpt(TimeSeries, "TS:")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update([(self.acquire_mode, "Single")])  # single mode
        self.configuration_attrs = [
            "integration_time",
            "averaging_time",
            "em_range",
            "num_averaged",
            "values_per_read",
            "trigger_mode",
        ]
    
class LiXTetrAMMext(QuadEM):
    conf = Cpt(QuadEMPort, port_name="TetrAMM", kind="omitted")
    ts = ADCpt(TimeSeries, "TS:")
    npoints = Signal(name="num_points", value=20)
    avg_time = Signal(name="avg_time", value=0.05)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fstatus = None
        self.rep = 1
        self.stage_sigs.update([('acquire_mode', 0), # continuous 
                                ('trigger_mode', 1), # ext trigger
                                ('ts.acquire_mode', 1), # circular buffer
                                ('ts.read_rate', 0), # passive
                               ])
        self.configuration_attrs = [
            "integration_time",
            "averaging_time",
            "em_range",
            "num_averaged",
            "values_per_read",
            "trigger_mode",
        ]
    
    def stage(self):
        self.stage_sigs.update([('averaging_time', self.avg_time.get()),
                                ('ts.averaging_time', self.avg_time.get()),
                                ('ts.num_points', self.npoints.get()),
                               ])
        super().stage()
        self.read_back = {'data': [], 'ts': []}
    
    def kickoff(self):
        print("kicking off emext ...")
        self._fstatus = DeviceStatus(self)

        self.ts.acquire.set(1).wait()
        time.sleep(0.1)
        self.acquire.set(1).wait()
       
        print("emext kicked off ...")
        return self._fstatus
        #return NullStatus()
        
    def complete(self):
        print("compelting emext ...")
        if self._fstatus is None:
            raise RuntimeError("must call kickoff() before complete()")

        self.ts.acquire.set(0).wait()
        caput(self.ts.prefix+"TSRead", 1)
        time.sleep(0.2)
        em2d = self.ts.SumAll.read()[f'{self.name}_ts_SumAll']
        #self.read_back['data'].extend(em2d['value'][:self.npoints.get()])  
        self.read_back['data'].append(np.asarray(em2d['value'][:self.npoints.get()]))  
        self.read_back['ts'].append(em2d['timestamp'])        

        self._fstatus._finished()
        print("emext compelte done")
        return self._fstatus
        #return NullStatus()
    
    def collect(self):
        print("in em collect ...")
        k = self.ts.SumAll.name
        yield  {'time': time.time(),
                'data': {k: np.array(self.read_back['data'])},
                'timestamps': {k: self.read_back['ts']},
                }   
        
    def describe_collect(self):
        print("in em describe_collect ...")
        ret = self.ts.SumAll.describe()
        for k in ret.keys():
            ret[k]['shape'] = [self.rep, ret[k]['shape'][0]]

        #return {'primary': ret}
        return {self.name: ret}
       
#em1 = LiX_EM('XF:16IDC-ES{NSLS_EM:1}', name='em1')
em1 = LiXTetrAMM('XF:16IDC-BI{BPM:1}', name='em1')
em1.read_attrs = ['current1', 'current2', 'current3', 'current4', 'sum_all']
em1.sum_all.mean_value.kind = 'hinted'

# Siddons electrometer
#em2 = LiX_EM('XF:16IDC-ES{NSLS_EM:2}', name='em2')
#em2.read_attrs = ['current1', 'current2', 'current3', 'current4', 'sum_all']
#em2.sum_all.mean_value.kind = 'hinted'

# CaenELS TetrAMM
em2 = LiXTetrAMM('XF:16IDC-BI{BPM:2}', name='em2')
em2.read_attrs = ['sum_all']
em2.sum_all.mean_value.kind = 'hinted'

# this is used when em2 is used in fly scans
em2ext = LiXTetrAMMext('XF:16IDC-BI{BPM:1}', name='em2')
em2ext.read_attrs = ['sum_all']
em2ext.sum_all.mean_value.kind = 'hinted'

em0 = LiX_EM('XF:16IDA{NSLS_EM:3}', name='em0')
em0.read_attrs = ['x_position', 'y_position']

#tetramm = TetrAMM('XF:16IDC-ES{TETRAMM:1}', name='tetramm')
bpm = Best('XF:16IDB-CT{Best}', name='bpm')

def start_monitor(monitors=[em1], rate=20):
    for em in monitors: 
        em.acquire_mode.set(0).wait()   # continuous
        em.trigger_mode.set(0).wait()   # free run
        em.averaging_time.put(1./rate)  
        em.ts.averaging_time.put(1./rate)  
        em.ts.num_points.put(rate)  
        em.ts.acquire_mode.put(1)       # circular buffer
        em.ts.read_rate.put(6)          # 1 second
        em.acquire.put(1)
        em.ts.acquire.put(1)
