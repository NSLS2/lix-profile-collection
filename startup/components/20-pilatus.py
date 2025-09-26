print(f"Loading {__file__}...")

from ophyd import ( Component as Cpt, ADComponent, Signal,
                    EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV,
                    ROIPlugin, StatsPlugin, ImagePlugin,
                    SingleTrigger, PilatusDetector, Device)

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

from ophyd.areadetector.cam import PilatusDetectorCam as _PilatusDetectorCam

class LIXPilatusCam(_PilatusDetectorCam):
    full_file_name = ADComponent(EpicsSignalRO, 'FullFileName_RBV', string=True)
    
class LIXPilatus(PilatusDetector):
    _num_captures = 0    # hdf plugin to accept infinite number of frames
    cam = ADComponent(LIXPilatusCam, 'cam1:')
    #pva = Cpt(PvaPlugin, "Pva1:")
    hdf = Cpt(LIXhdfPlugin, suffix="HDF1:", write_path_template="", root='/')
    codec1 = Cpt(CodecPlugin, "Codec1:")
    
    cbf_file_path = ADComponent(EpicsSignalWithRBV, 'cam1:FilePath', string=True)
    cbf_file_name = ADComponent(EpicsSignalWithRBV, 'cam1:FileName', string=True)
    cbf_file_number = ADComponent(EpicsSignalWithRBV, 'cam1:FileNumber')
    HeaderString = Cpt(EpicsSignal, "cam1:HeaderString")
    ThresholdEnergy = Cpt(EpicsSignal, "cam1:ThresholdEnergy")
    armed = Cpt(EpicsSignal, "cam1:Armed")
    detstate = Cpt(EpicsSignal,"cam1:DetectorState_RBV")

    def make_data_key(self):
        ret = super().make_data_key()
        color_mode = self.cam.color_mode.get(as_string=True)
        if color_mode == 'Mono':
            ret['shape'] = [
                # TODO paramaterize this better
                1,
                self.hdf.array_size.height.get(),
                self.hdf.array_size.width.get()
                ]
            ret['dims'] = ['frame', 'y', 'x']
        else:
            raise RuntimeError("SHould never be here")

        cam_dtype = self.cam.data_type.get(as_string=True)
        type_map = {'UInt8': '|u1', 'UInt16': '<u2', 'Float32':'<f4', "Float64":'<f8', 'Int8': '<i4'}
        if cam_dtype in type_map:
            ret['dtype_str'] = type_map[cam_dtype]
        return ret
    
    def __init__(self, *args, hostname, detector_id, **kwargs):
        self.detector_id = detector_id
        self.hostname = hostname
        super().__init__(*args, **kwargs)

        self._acquisition_signal = self.cam.acquire
        self._counter_signal = self.cam.array_counter
        self.set_cbf_file_default(f"/ramdisk/{self.name}/", "current")
        self.hdf.data_dir = pilatus_data_dir
        self._num_repeats = 1
        self._num_images = 1
        self.ts = []

        if self.hdf.run_time.get()==0: # first time using the plugin
            self.hdf.warmup()

    def update_cbf_name(self, cn=None):
        if cn is None:
            #ts = time.localtime()
            #cn = f"{ts.tm_year}-{ts.tm_mon:02d}-{ts.tm_mday:02d}.{ts.tm_hour:02d}{ts.tm_min:02d}{ts.tm_sec:02d}"
            cn = time.asctime().replace(" ","_").replace(":", "")
        self.set_cbf_file_default(f"/ramdisk/{self.name}/", cn)

    def set_cbf_file_default(self, path, fn):
        self.cbf_file_path.put(path, wait=True)
        self.cbf_file_name.put(fn, wait=True)

    def set_thresh(self, ene):
        """ set threshold
        """
        if self.cam.acquire.get()==0 and self.cam.armed.get()==0:
        #if self.cam.detstate.get()==0 and self.cam.armed.get()==0:
            #print(self.cam.armed.get())
            #print(self.cam.detstate.get())
            self.ThresholdEnergy.put(ene, wait=True)
            self.cam.threshold_apply.put(1)
        else:
            ene = pseudoE.energy.position/1000
            eth = self.ThresholdEnergy.get()
            print(f"Threshold is not set for {self.name} due to active data collection.")
            print(f"x-ray enegy = 2x {ene/2:.2f} keV, threshold is at {eth:.2f} keV")

    def stage(self, trigger_mode):
        if self._staged == Staged.yes:
            return

        self.trigger_mode = trigger_mode
        if trigger_mode is PilatusTriggerMode.ext:
            self.cam.num_images.put(self._num_images*self._num_repeats,
                                    wait=True)
        else:
            self.cam.num_images.put(self._num_images, wait=True)
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

        self.ts = []
        print(self.name, "staged")

    def unstage(self, timeout=5):
        if self._staged == Staged.no:
            return

        print(self.name, "unstaging ...")
        print(self.name, "checking detector Armed status:", end="")
        ts0 = time.time()
        st = None
        while self.armed.get():
            time.sleep(0.2)
            if time.time()-ts0>timeout and st is None:
                st = self.cam.acquire.set(0)
                print(f"force stop {self.name}")
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
        self.generate_datum(f'{self.name}_image', ttime.time())


class LiXDetectors(Device):
    pil1M = Cpt(LIXPilatus, '{Det:SAXS}', name="pil1M", detector_id="SAXS", hostname="xf16idc-pilatus1m.nsls2.bnl.local")
    #pilW1 = Cpt(LIXPilatus, '{Det:WAXS1}', name="pilW1", detector_id="WAXS1", hostname="xf16idc-pilatus300k1.nsls2.bnl.local")
    pilW2 = Cpt(LIXPilatus, '{Det:WAXS2}', name="pilW2", detector_id="WAXS2", hostname="xf16idc-pilatus900k.nsls2.bnl.local")
    trigger_lock = None
    reset_file_number = True
    _num_images = 1
    _num_repeats = 1
    active_detectors = []
    trig_wait = 1.
    acq_time = 1.
    trigger_mode = PilatusTriggerMode.soft
    _trigger_width = 0.002

    def __init__(self, prefix):
        super().__init__(prefix=prefix, name="pil")
        self.dets = {"pil1M": self.pil1M,  "pilW2": self.pilW2} # "pilW1": self.pilW1,
        #self.dets = {"pilW2": self.pilW2}
        if self.trigger_lock is None:
            self.trigger_lock = threading.Lock()
        for dname,det in self.dets.items():
            det.name = dname
            det.read_attrs = ['hdf'] #['file']
        self.active_detectors = list(self.dets.values())
        self.trigger_time = Signal(name="pilatus_trigger_time")

        self._trigger_signal = EpicsSignal('XF:16IDC-ES{Zeb:1}:SOFT_IN:B0')
        self._exp_completed = 0
        self._flying = False

        RE.md['pilatus'] = {}
        RE.md['pilatus']['ramdisk'] = pilatus_data_dir

        # ver 0, or none at all: filename template must be set by CBF file handler
        # ver 1: filename template is already revised by the file plugin
        #RE.md['pilatus']['cbf_file_handler_ver'] = 0

    def update_cbf_name(self, cn=None):
        for det in self.active_detectors:
            det.update_cbf_name(cn)

    def update_header(self, hdr_str):
        for det in self.active_detectors:
            det.HeaderString.put(hdr_str)

    def activate(self, det_list):
        """ e.g.
            activate(['pil1M', 'pilW2'])
        """
        for det in det_list:
            if det not in self.dets.keys():
                raise Exception(f"{det} is not a known Pilatus detector.")
        self.active_detectors = [self.dets[d] for d in det_list]
        RE.md['pilatus']['active_detectors'] = [d.name for d in self.active_detectors]

    def set_trigger_mode(self, trigger_mode):
        if isinstance(trigger_mode, PilatusTriggerMode):
            self.trigger_mode = trigger_mode
        else:
            print(f"invalid trigger mode: {trigger_mode}")
        RE.md['pilatus']['trigger_mode'] = trigger_mode.name

    def set_num_images(self, num, rep=1):
        self._num_images = num
        self._num_repeats = rep
        RE.md['pilatus']['num_images'] = [num, rep]

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
            self.dets[det_name].cam.acquire_period.put(exp+self._trigger_width)
        self.acq_time = exp+self._trigger_width
        RE.md['pilatus']['exposure_time'] = exp


    def use_sub_directory(self, sd=None):
        if sd is not None:
            if sd[-1]!='/':
                sd += '/'
            #makedirs(data_path+sd, mode=0o0777)
            LIXhdfPlugin.sub_directory = sd
            RE.md['subdir'] = LIXhdfPlugin.sub_directory
        elif 'subdir' in RE.md.keys():
            del RE.md['subdir'] 
            LIXhdfPlugin.sub_directory = sd

    def set_thresh(self):
        ene = int(pseudoE.energy.position/100*0.5+0.5)*0.1
        for det in self.active_detectors: #self.dets.values():
            det.set_thresh(ene)

    def stage(self):
        if self._staged == Staged.yes:
            return
        change_path()
        # sc 11/12/24
        #for det in self.active_detectors:
        #    det.update_cbf_name(current_sample)
        #self.update_cbf_name(cn=current_sample)
        # sc 11/12/24
        fno = np.max([det.cbf_file_number.get() for det in self.dets.values()])
        if self.reset_file_number:
            fno = 1
        for det in self.dets.values():
            det.cbf_file_number.put(fno+1)

        for det in self.active_detectors:
            det._num_images = self._num_images
            det._num_repeats = self._num_repeats
            det.stage(self.trigger_mode)

        if self.trigger_mode == PilatusTriggerMode.ext_multi:
            # the name is misleading, multi_triger means one image per trigger
            self.trig_wait = self.acq_time   #+0.02
        else:
            self.trig_wait = self.acq_time*self._num_images*self._num_repeats   #+0.02
        
        self.datum={}

    def unstage(self):
        self._flying = False
        for det in self.active_detectors:
            det.unstage()

    def trigger(self):
        #if len(self.active_detectors)==0:
        #    return
        self._status = DeviceStatus(self)
        if self.trigger_mode is not PilatusTriggerMode.soft and not self._flying:
            while self.trigger_lock.locked():
                time.sleep(self._trigger_width)
            self.trigger_time.put(time.time())
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

#    def describe(self):
#        """ aim to reduce the amount of information saved in the databroker
#            all detectors share the same name, path and template
#            in fact these are the same for the entire scan
#        """
#        attrs = OrderedDict([])
#        common_attrs = self.active_detectors[0].describe()

    def collect_asset_docs(self):
        print(f"in {self.name} collect_asset_docs")
        for det in self.active_detectors:
            yield from det.collect_asset_docs()

    def kickoff(self):
        return NullStatus()
        
    def complete(self):
        ''' prepare asset_docs_cache() to be collected
        
            when the run eigine process the "collect" message, 3 functions are called (see bluesky.bundlers)
                collect_asset_docs(): returns resource and datum document (name, doc)
                                      RE emit(DocumentNames(name), doc)
                                      called once per scan? name is always "resource"?
                describe_collect(): returns a dictionary of {stream_name: data_keys, ...}
                                    RE emit(DocumentNames.descriptor, doc) 
                collect(): returns a list of events [ev, ...], 
                           RE emit(DocumentNames.event, ev) or add to bulk data for later emit() call
            DocumentNames is defined in event_model, enum

            following HXN example
        '''
        print(f"in {self.name} complete ...")

        for det in self.active_detectors:
            k = f'{det.name}_image'
            print(list(det.hdf._asset_docs_cache))
            (name, resource), = det.hdf.collect_asset_docs()
            assert name == 'resource'
            # hack the resource
            resource['resource_kwargs']['frame_per_point'] = self._num_images
            det.hdf._asset_docs_cache.append(('resource', resource))
            resource_uid = resource['uid']
            datum_id = '{}/{}'.format(resource_uid, 0)
            #datum_id = resource_uid
            self.datum[k] = [datum_id, ttime.time()]
            datum = {'resource': resource_uid,
                     'datum_id': datum_id,
                     'datum_kwargs': {'point_number': 0}}
            det.hdf._asset_docs_cache.append(('datum', datum))     # the scattering patterns go to the hdf plugin asset_docs_cache

        print("+++", det.hdf._asset_docs_cache)
        print("---", self.datum)   
        return NullStatus()

    def collect(self):
        print(f"in {self.name} collect ...")
        data = {}
        ts = {}
        for det in self.active_detectors:
            k = f'{det.name}_image'
            data[k],ts[k] = self.datum[k]
        
        ret = {'time': time.time(),
               'data': data,
               'timestamps': ts,
              }
        yield ret

    def describe_collect(self):
        print(f"in {self.name} describe_collect ...")
        ret = {}
        for det in self.active_detectors:
            ret[f'{det.name}_image'] = det.make_data_key()
            ret[f'{det.name}_image']['shape'] = (self._num_images, *ret[f'{det.name}_image']['shape'][1:])
            for k,desc in det.describe().items():
                ret[k] = desc
        #return {'primary': ret}
        return {self.name: ret}
                                    
try:
    pil = LiXDetectors("XF:16IDC-DT")   
    pil.activate(["pil1M", "pilW2"])
    if pil.active_detectors[0].armed.get()==0:
        pil.set_trigger_mode(PilatusTriggerMode.ext_multi)
        #pil.set_thresh()
except:
    print("Unable to initialize the Pilatus detectors ...")

