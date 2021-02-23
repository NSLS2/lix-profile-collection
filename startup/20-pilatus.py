from ophyd import ( Component as Cpt, ADComponent, Signal,
                    EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV,
                    ROIPlugin, StatsPlugin, ImagePlugin,
                    SingleTrigger, PilatusDetector, Device)

from ophyd.areadetector.filestore_mixins import FileStoreIterativeWrite

from ophyd.utils import set_and_wait
from databroker.assets.handlers_base import HandlerBase
from ophyd.device import Staged
from pathlib import Path

import os,time,threading
from types import SimpleNamespace

from enum import Enum
class PilatusTriggerMode(Enum):
    soft = 0        # Software 
    ext = 2         # ExtTrigger in camserver
    ext_multi = 3   # ExtMTrigger in camserver

class PilatusFilePlugin(Device, FileStoreIterativeWrite):
    file_path = ADComponent(EpicsSignalWithRBV, 'FilePath', string=True)
    file_number = ADComponent(EpicsSignalWithRBV, 'FileNumber')
    file_name = ADComponent(EpicsSignalWithRBV, 'FileName', string=True)
    file_template = ADComponent(EpicsSignalWithRBV, 'FileTemplate', string=True)
    file_number_reset = 1
    next_file_number = 1
    sub_directory = None
    froot = data_file_path.gpfs
    enable = SimpleNamespace(get=lambda: True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._datum_kwargs_map = dict()  # store kwargs for each uid
        self.filestore_spec = 'AD_CBF'

    def stage(self):
        global proposal_id
        global run_id
        global current_sample
        global data_path

        f_tplt = '%s%s_%06d_'+self.parent.detector_id+'.cbf'
        set_and_wait(self.file_template, f_tplt, timeout=99999)

        if PilatusFilePlugin.sub_directory is not None:
            f_path = data_path+PilatusFilePlugin.sub_directory
        else:
            f_path = data_path

        f_fn = current_sample
        print('%s: setting file path ...' % self.name)
        if self.froot == data_file_path.ramdisk:
            f_path = f_path.replace(data_file_path.gpfs.value, data_file_path.ramdisk.value) 
        set_and_wait(self.file_path, f_path, timeout=99999) 
        set_and_wait(self.file_name, f_fn, timeout=99999)
        self._fn = Path(f_path)

        fpp = self.get_frames_per_point()
        # when camserver collects in "multiple" mode, another number is added to the file name
        # even though the template does not specify it. 
        # Camserver doesn't like the template to include the second number
        # The template will be revised in the CBF handler if fpp>1

        print('%s: super().stage() ...' % self.name)
        super().stage()
        res_kwargs = {'template': f_tplt, # self.file_template(),
                      'filename': f_fn, # self.file_name(),
                      'frame_per_point': fpp,
                      'initial_number': self.file_number.get()}
        print('%s: _generate_resource() ...' % self.name)
        self._generate_resource(res_kwargs)

    def unstage(self):
        super().unstage()

    def get_frames_per_point(self):
        return self.parent.parent._num_images

class LIXPilatus(PilatusDetector):
    file = Cpt(PilatusFilePlugin, suffix="cam1:",
               write_path_template="", root='/')

    #roi1 = Cpt(ROIPlugin, 'ROI1:')
    #roi2 = Cpt(ROIPlugin, 'ROI2:')
    #roi3 = Cpt(ROIPlugin, 'ROI3:')
    #roi4 = Cpt(ROIPlugin, 'ROI4:')

    #stats1 = Cpt(StatsPlugin, 'Stats1:')
    #stats2 = Cpt(StatsPlugin, 'Stats2:')
    #stats3 = Cpt(StatsPlugin, 'Stats3:')
    #stats4 = Cpt(StatsPlugin, 'Stats4:')

    HeaderString = Cpt(EpicsSignal, "cam1:HeaderString")
    ThresholdEnergy = Cpt(EpicsSignal, "cam1:ThresholdEnergy")
    armed = Cpt(EpicsSignal, "cam1:Armed")

    def __init__(self, *args, detector_id, **kwargs):
        self.detector_id = detector_id
        super().__init__(*args, **kwargs)
        
        self._acquisition_signal = self.cam.acquire
        self._counter_signal = self.cam.array_counter

    def set_thresh(self, ene):
        """ set threshold
        """
        set_and_wait(self.ThresholdEnergy, ene)
        self.cam.threshold_apply.put(1)

    def stage(self, trigger_mode):
        if self._staged == Staged.yes:
            return

        self.trigger_mode = trigger_mode
        if trigger_mode is PilatusTriggerMode.ext:
            self.cam.num_images.put(self.parent._num_images*self.parent._num_repeats,
                                    wait=True)
        else:
            self.cam.num_images.put(self.parent._num_images, wait=True)
        print(self.name, f" staging for {trigger_mode}")
        self.cam.trigger_mode.put(trigger_mode.value, wait=True)
        super().stage()
        print(self.name, "super staged")

        if trigger_mode is PilatusTriggerMode.soft:  
            self._acquisition_signal.subscribe(self.parent._acquire_changed)
        else: # external triggering 
            self._counter_signal.put(0)
            time.sleep(.1)
            print(self.name, "checking armed status")
            self._acquisition_signal.put(1) #, wait=True)
            while self.armed.get() != 1:
                time.sleep(0.1)

        print(self.name, "staged")
        
    def unstage(self):
        if self._staged == Staged.no:
            return
        print(self.name, "unstaging ...")
        print(self.name, "checking detector Armed status:", end="")
        while self.armed.get():
            time.sleep(0.1)
        print(" unarmed.")
        if self.parent.trigger_mode is PilatusTriggerMode.soft:  
            self._acquisition_signal.clear_sub(self.parent._acquire_changed)
        else:
            self._acquisition_signal.put(0, wait=True)
            self.cam.trigger_mode.put(0, wait=True)   # always set back to software trigger
            self.cam.num_images.put(1, wait=True)
        super().unstage()
        print(self.name, "unstaging completed.")
            
    def trigger(self):
        if self._staged != Staged.yes:
            raise RuntimeError("This detector is not ready to trigger."
                               "Call the stage() method before triggering.")
        print(self.name+" trigger")
        if self.trigger_mode is PilatusTriggerMode.soft:
            self._acquisition_signal.put(1, wait=False)
        self.dispatch(f'{self.name}_image', ttime.time())

            
class LiXPilatusDetectors(Device):
    pil1M = Cpt(LIXPilatus, '{Det:SAXS}', name="pil1M", detector_id="SAXS")
    pilW1 = Cpt(LIXPilatus, '{Det:WAXS1}', name="pilW1", detector_id="WAXS1")
    pilW2 = Cpt(LIXPilatus, '{Det:WAXS2}', name="pilW2", detector_id="WAXS2")
    trigger_lock = None
    reset_file_number = True
    _num_images = 1
    _num_repeats = 1
    active_detectors = []
    trig_wait = 1.
    acq_time = 1.
    trigger_mode = PilatusTriggerMode.soft
    
    def __init__(self, prefix):
        super().__init__(prefix=prefix, name="pil")
        self.dets = {"pil1M": self.pil1M, "pilW1": self.pilW1, "pilW2": self.pilW2}
        if self.trigger_lock is None:
            self.trigger_lock = threading.Lock()
        for dname,det in self.dets.items():
            det.name = dname
            det.read_attrs = ['file']
        self.active_detectors = list(self.dets.values())
            
        self._trigger_signal = EpicsSignal('XF:16IDC-ES{Zeb:1}:SOFT_IN:B0')
        self._exp_completed = 0
        if not "pilatus" in RE.md.keys():
            RE.md['pilatus'] = {}
        # ver 0, or none at all: filename template must be set by CBF file handler
        # ver 1: filename template is already revised by the file plugin
        RE.md['pilatus']['cbf_file_handler_ver'] = 0 
        self.set_trigger_mode(PilatusTriggerMode.soft)
        
    def update_header(self, uid):
        for det in self.active_detectors:
            det.HeaderString.put(f"uid={uid}")

    def activate(self, det_list):
        """ e.g.
            activate(['pil1M', 'pilW2'])
        """
        for det in det_list:
            if det not in self.dets.keys():
                raise Exception(f"{det} is not a known Pilatus detector.")
        self.active_detectors = [self.dets[d] for d in det_list]
    
    def set_trigger_mode(self, trigger_mode):
        if isinstance(trigger_mode, PilatusTriggerMode):
            self.trigger_mode = trigger_mode
        else: 
            print(f"invalid trigger mode: {trigger_mode}")
        RE.md['pilatus']['trigger_mode'] = trigger_mode.name
        
    def set_num_images(self, num, rep=1):
        self._num_images = num
        self._num_repeats = rep
        
    def number_reset(self, reset=True):
        self.reset_file_number = reset
        for det in self.dets.values():
            det.file.file_number.put(0)
        
    def exp_time(self, exp):
        for det_name in self.dets.keys():
            self.dets[det_name].read_attrs = ['file']
            self.dets[det_name].cam.acquire_time.put(exp)
            self.dets[det_name].cam.acquire_period.put(exp+0.005)
        self.acq_time = exp+0.005

    def use_sub_directory(self, sd=None):
        if sd is not None:
            if sd[-1]!='/':
                sd += '/'
            makedirs(data_path+sd, mode=0o0777)
            RE.md['subdir'] = PilatusFilePlugin.sub_directory
            PilatusFilePlugin.sub_directory = sd
        elif 'subdir' in RE.md.keys():
            del RE.md['subdir'] 
            PilatusFilePlugin.sub_directory = sd
        
    def set_thresh(self):
        ene = int(pseudoE.energy.position/10*0.5+0.5)*0.01
        for det in self.dets.values():
            det.set_thresh(ene)
            
    def stage(self):
        if self._staged == Staged.yes:
            return
        change_path()
        fno = np.max([det.file.file_number.get() for det in self.dets.values()])        
        if self.reset_file_number:
            fno = 1
        for det in self.dets.values():
            det.file.file_number.put(fno)
            
        for det in self.active_detectors:
            det.stage(self.trigger_mode)
            
        if self.trigger_mode == PilatusTriggerMode.ext_multi:
            # the name is misleading, multi_triger means one image per trigger
            self.trig_wait = self.acq_time+0.02
        else:
            self.trig_wait = self.acq_time*self._num_images+0.02
        
    def unstage(self):
        for det in self.active_detectors:
            det.unstage()
                
    def trigger(self):
        #if len(self.active_detectors)==0:
        #    return
        self._status = DeviceStatus(self)
        if self.trigger_mode is not PilatusTriggerMode.soft:  
            while self.trigger_lock.locked():
                time.sleep(0.005)
            print("generating triggering pulse ...")
            self._trigger_signal.put(1, wait=True)
            self._trigger_signal.put(0, wait=True)
        for det in self.active_detectors:
            det.trigger()
        if self.trigger_mode is not PilatusTriggerMode.soft:
            # soft: status to be cleared by _acquire_changed()
            # ext: set up callback to clear status after the end-of-exposure
            threading.Timer(self.trig_wait, self._status._finished, ()).start()
        # should advance the file number in external trigger mode???
        
        return self._status
    
    def repeat_ext_trigger(self, rep):
        """ this is used to produce external triggers to complete data collection by camserver
        """
        for i in reversed(range(rep)):
            self._trigger_signal.put(1, wait=True)
            self._trigger_signal.put(0, wait=True)
            time.sleep(self.acq_time)
            print(f"# of triggers to go: {i} \r", end="")

    def _acquire_changed(self, value=None, old_value=None, **kwargs):
        if old_value==1 and value==0:
            self._exp_completed += 1
        if self._exp_completed==len(self.active_detectors):
            self._exp_completed = 0
            self._status._finished()

    def collect_asset_docs(self):
        for det in self.active_detectors:
            yield from det.collect_asset_docs()
    
#    def describe(self):
#        """ aim to reduce the amount of information saved in the databroker
#            all detectors share the same name, path and template
#            in fact these are the same for the entire scan
#        """
#        attrs = OrderedDict([])
#        common_attrs = self.active_detectors[0].describe()
        
                                    
try:
    pil = LiXPilatusDetectors("XF:16IDC-DT")   
    pil.activate(["pil1M", "pilW2"])
    pil.set_trigger_mode(PilatusTriggerMode.ext_multi)
except:
    print("Unable to initialize the Pilatus detectors ...")

