from ophyd import ( Component as Cpt, ADComponent, Signal,
                    EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV,
                    ROIPlugin, StatsPlugin, ImagePlugin,
                    SingleTrigger, PilatusDetector, Device)

from ophyd.areadetector.filestore_mixins import FileStoreBase,FileStoreHDF5,FileStoreIterativeWrite
from ophyd.areadetector.plugins import HDF5Plugin

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

class LiXFileStorePluginBase(FileStoreBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update([('auto_increment', 'Yes'),
                                ('array_counter', 0),
                                ('auto_save', 'Yes'),
                                ('num_capture', 0),
                                ])
        self._fn = None
        self._fp = None

    def make_filename(self):
        '''Make a filename.
        This is a hook so that the read and write paths can either be modified
        or created on disk prior to configuring the areaDetector plugin.
        Returns
        -------
        filename : str
            The start of the filename
        read_path : str
            Path that ophyd can read from
        write_path : str
            Path that the IOC can write to
        '''
        filename = new_short_uid()
        formatter = datetime.now().strftime
        write_path = formatter(self.write_path_template)
        read_path = formatter(self.read_path_template)
        return filename, read_path, write_path

    def stage(self):
        # Make a filename.
        filename, read_path, write_path = self.make_filename()

        # Ensure we do not have an old file open.
        if self.file_write_mode != 'Single':
            set_and_wait(self.capture, 0)
        # These must be set before parent is staged (specifically
        # before capture mode is turned on. They will not be reset
        # on 'unstage' anyway.
        self.file_path.set(write_path).wait()
        set_and_wait(self.file_name, filename)
        #set_and_wait(self.file_number, 0)     # only reason to redefine the pluginbase
        super().stage()

        # AD does this same templating in C, but we can't access it
        # so we do it redundantly here in Python.
        self._fn = self.file_template.get() % (read_path,
                                               filename,
                                               # file_number is *next* iteration
                                               self.file_number.get() - 1)
        self._fp = read_path
        if not self.file_path_exists.get():
            raise IOError("Path %s does not exist on IOC."
                          "" % self.file_path.get())


class LiXFileStoreHDF5(LiXFileStorePluginBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filestore_spec = 'AD_HDF5'  # spec name stored in resource doc
        self.stage_sigs.update([('file_template', '%s%s_%6.6d.h5'),
                                ('file_write_mode', 'Stream'),
                                ('capture', 1)
                                ])

    def get_frames_per_point(self):
        num_capture = self.num_capture.get()
        # If num_capture is 0, then the plugin will capture however many frames
        # it is sent. We can get how frames it will be sent (unless
        # interrupted) by consulting num_images on the detector's camera.
        if num_capture == 0:
            return self.parent.cam.num_images.get()
        # Otherwise, a nonzero num_capture will cut off capturing at the
        # specified number.
        return num_capture

    def stage(self):
        super().stage()
        res_kwargs = {'frame_per_point': self.get_frames_per_point()}
        self._generate_resource(res_kwargs)


class LIXhdfPlugin(HDF5Plugin, LiXFileStoreHDF5):
    sub_directory = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fnbr = 0        

    def make_filename(self):
        ''' replaces FileStorePluginBase.make_filename()
        Returns
        -------
        filename : str
            The start of the filename
        read_path : str
            Path that ophyd can read from
        write_path : str
            Path that the IOC can write to
        '''
        global data_path,current_sample
        
        filename = f"{current_sample}_{self.parent.detector_id}"
        write_path = data_path if self.sub_directory is None else f"{data_path}/self.{sub_directory}"
        read_path = write_path # might want to handle this differently, this shows up in res/db
        #read_path = self.parent.cbf_file_path.get()
        return filename, read_path, write_path
    
    #def stage(self):
    #    """ need to set the number of images to collect and file path
    #    """
    #    super().stage()
    #    if not self.parent.parent.reset_file_number:
    #        set_and_wait(self.file_number, self.fnbr+1)
    #        filename, read_path, write_path = self.make_filename()
    #        self._fn = self.file_template.get() % (read_path, filename, self.fnbr)
    #        set_and_wait(self.full_file_name, self._fn)
        
    #def unstage(self):
    #    self.fnbr = self.file_number.get()
    #    super().unstage()
        
    def get_frames_per_point(self):
        if self.parent.trigger_mode is PilatusTriggerMode.ext:
            return self.parent.parent._num_images
        else:
            return 1
    
class LIXPilatus(PilatusDetector):
    hdf = Cpt(LIXhdfPlugin, suffix="HDF1:",
              write_path_template="", root='/')
    
    cbf_file_path = ADComponent(EpicsSignalWithRBV, 'cam1:FilePath', string=True)
    cbf_file_name = ADComponent(EpicsSignalWithRBV, 'cam1:FileName', string=True)
    cbf_file_number = ADComponent(EpicsSignalWithRBV, 'cam1:FileNumber')
    HeaderString = Cpt(EpicsSignal, "cam1:HeaderString")
    ThresholdEnergy = Cpt(EpicsSignal, "cam1:ThresholdEnergy")
    armed = Cpt(EpicsSignal, "cam1:Armed")
    flatfield = Cpt(EpicsSignal, "cam1:FlatFieldFile")

    def __init__(self, *args, detector_id, **kwargs):
        self.detector_id = detector_id
        super().__init__(*args, **kwargs)
        
        self._acquisition_signal = self.cam.acquire
        self._counter_signal = self.cam.array_counter
        self.set_cbf_file_default("/exp_path/current", "current")  # local to the detector server
        self.hdf.warmup()
        
    def set_flatfield(self, fn):
        """ do some changing first
            make sure that the image size is correct and the values are reasonable
            
            documentation on the PV:
            
            Name of a file to be used to correct for the flat field. If this record does not point to a valid 
            flat field file then no flat field correction is performed. The flat field file is simply a TIFF 
            or CBF file collected by the Pilatus that is used to correct for spatial non-uniformity in the 
            response of the detector. It should be collected with a spatially uniform intensity on the detector 
            at roughly the same energy as the measurements being corrected. When the flat field file is read, 
            the average pixel value (averageFlatField) is computed using all pixels with intensities 
            >PilatusMinFlatField. All pixels with intensity <PilatusMinFlatField in the flat field are replaced 
            with averageFlatField. When images are collected before the NDArray callbacks are performed the following 
            per-pixel correction is applied:
                ImageData[i] = (averageFlatField * ImageData[i])/flatField[i];
            or
                ImageData[i] *= averageFlatField/flatField[i]
        """ 
        self.flatfield.put(fn, wait=True)
    
    def set_cbf_file_default(self, path, fn):
        self.cbf_file_path.put(path, wait=True)
        self.cbf_file_name.put(fn, wait=True)

    def set_thresh(self, ene):
        """ set threshold
        """
        self.ThresholdEnergy.put(ene, wait=True)
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

            
class LiXDetectors(Device):
    pil1M = Cpt(LIXPilatus, '{Det:SAXS}', name="pil1M", detector_id="SAXS")
    #pilW1 = Cpt(LIXPilatus, '{Det:WAXS1}', name="pilW1", detector_id="WAXS1")
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
        self.dets = {"pil1M": self.pil1M,  "pilW2": self.pilW2} # "pilW1": self.pilW1,
        if self.trigger_lock is None:
            self.trigger_lock = threading.Lock()
        for dname,det in self.dets.items():
            det.name = dname
            det.read_attrs = ['hdf'] #['file']
        self.active_detectors = list(self.dets.values())
            
        self._trigger_signal = EpicsSignal('XF:16IDC-ES{Zeb:1}:SOFT_IN:B0')
        self._exp_completed = 0
        if not "pilatus" in RE.md.keys():
            RE.md['pilatus'] = {}
        # ver 0, or none at all: filename template must be set by CBF file handler
        # ver 1: filename template is already revised by the file plugin
        #RE.md['pilatus']['cbf_file_handler_ver'] = 0 
        
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
        if reset:
            for det in self.dets.values():
                det.cbf_file_number.put(0)
                det.hdf.file_number.put(0)
        
    def exp_time(self, exp):
        for det_name in self.dets.keys():
            self.dets[det_name].read_attrs = ['hdf']
            self.dets[det_name].cam.acquire_time.put(exp)
            self.dets[det_name].cam.acquire_period.put(exp+0.005)
        self.acq_time = exp+0.005

    def use_sub_directory(self, sd=None):
        if sd is not None:
            if sd[-1]!='/':
                sd += '/'
            makedirs(data_path+sd, mode=0o0777)
            RE.md['subdir'] = LIXhdfPlugin.sub_directory
            LIXhdfPlugin.sub_directory = sd
        elif 'subdir' in RE.md.keys():
            del RE.md['subdir'] 
            LIsXhdfPlugin.sub_directory = sd
        
    def set_thresh(self):
        ene = int(pseudoE.energy.position/10*0.5+0.5)*0.01
        for det in self.dets.values():
            det.set_thresh(ene)
            
    def stage(self):
        if self._staged == Staged.yes:
            return
        change_path()
        fno = np.max([det.cbf_file_number.get() for det in self.dets.values()])        
        if self.reset_file_number:
            fno = 1
        for det in self.dets.values():
            det.cbf_file_number.put(fno+1)
            
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
    pil = LiXDetectors("XF:16IDC-DT")   
    pil.activate(["pil1M", "pilW2"])
    pil.set_trigger_mode(PilatusTriggerMode.ext_multi)
    #pil.pilW2.flatfield.put("/home/det/WAXS2ff_2020Oct26.tif")
except:
    print("Unable to initialize the Pilatus detectors ...")

