from ophyd import ( Component as Cpt, ADComponent,
                    EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV,
                    ROIPlugin, StatsPlugin, ImagePlugin,
                    SingleTrigger, PilatusDetector, Device)

# deprecated
#from ophyd.areadetector.filestore_mixins import FileStoreBulkWrite
from ophyd.areadetector.filestore_mixins import FileStoreIterativeWrite

from ophyd.utils import set_and_wait
from databroker.assets.handlers_base import HandlerBase
from ophyd.device import Staged


# shortcut to databroker registry
reg = db.reg

import fabio
import os,time,threading
from threading import Timer
from types import SimpleNamespace

def first_Pilatus():
    #print("checking first Pialtus")
    for det in DETS:
        if det.__class__ == LIXPilatus:
            #print(det.name)
            return det.name
    return None

def first_PilatusExt():
    #print("checking first Pialtus")
    for det in reversed(DETS):
        if det.__class__ == LIXPilatusExt:
            #print(det.name)
            return det.name
    return None

class PilatusFilePlugin(Device, FileStoreIterativeWrite):
    file_path = ADComponent(EpicsSignalWithRBV, 'FilePath', string=True)
    file_number = ADComponent(EpicsSignalWithRBV, 'FileNumber')
    file_name = ADComponent(EpicsSignalWithRBV, 'FileName', string=True)
    file_template = ADComponent(EpicsSignalWithRBV, 'FileTemplate', string=True)
    enable = SimpleNamespace(get=lambda: True)
    
    # this is not necessary to record since it contains the UID for the scan, useful 
    # to save in the CBF file but no need in the data store
    #file_header = ADComponent(EpicsSignal, "HeaderString", string=True) 
    
    # this is not necessary to record in the data store either, move to the parent 
    #reset_file_number = Cpt(Signal, name='reset_file_number', value=1)
    
    #filemover_files = Cpt(EpicsSignal, 'filemover.filename')
    #filemover_target_dir = Cpt(EpicsSignal, 'filemover.target')
    #filemover_move = Cpt(EpicsSignal, 'filemover.moving')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._datum_kwargs_map = dict()  # store kwargs for each uid

    def stage(self):
        global proposal_id
        global run_id
        global current_sample
        global data_path
        
        f_tplt = '%s%s_%06d_'+self.parent.detector_id+'.cbf'
        set_and_wait(self.file_template, f_tplt, timeout=99999)
        if self.parent.reset_file_number.get() == 1:
            set_and_wait(self.file_number, 1, timeout=99999)

        # original code by Hugo
        # this is done now when login()
        #path = '/GPFS/xf16id/exp_path/'
        #rpath = str(proposal_id)+"/"+str(run_id)+"/"
        #fpath = path + rpath
        #makedirs(fpath)
        
        # modified by LY
        # camserver saves data to the local ramdisk, a background process then move them to data_path
        # interesting to note that camserver saves the data to filename.tmp, then rename it filename after done writing
        # must have the '/' at the end, since camserver will add it to the RBV
        # this should done only once for all Pilatus detectors
        if self.parent.name == first_Pilatus() or self.parent.name == first_PilatusExt():
            #print("first Pilatus is %s" % self.parent.name)
            change_path()
        
        #set_and_wait(self.file_path, "/ramdisk/", timeout=99999) # 12/19/17, changed back to GPFS
        f_path = data_path
        f_fn = current_sample
        set_and_wait(self.file_path, f_path, timeout=99999)# 12/19/17, changed back to GPFS
        set_and_wait(self.file_name, f_fn, timeout=99999)
                
        fpp = self.get_frames_per_point()
        # when camserver collects in "multiple" mode, another number is added to the file name
        # even though the template does not specify it. The template cannot be changed to add this
        # second number. The template will be revised in the CBF handler if fpp>1
        #if fpp>1:
        #    f_tplt = '%s%s_%06d_'+self.parent.detector_id+'_%05d.cbf'

        super().stage()
        res_kwargs = {'template': f_tplt, # self.file_template(),  #
                      'filename': f_fn, # self.file_name(), 
                      'frame_per_point': fpp,
                      'initial_number': self.file_number.get()}
        #self._resource = reg.insert_resource('AD_CBF', rpath, res_kwargs, root=path)
        self._resource = reg.insert_resource('AD_CBF', data_path, res_kwargs, root="/")
       
        try: # this is used by solution scattering only
            sol
        except NameError:
            pass
        else:
            if self.parent.name == first_Pilatus():
                caput("XF:16IDC-ES:Sol{ctrl}ready", 1)

    def unstage(self):        
        super().unstage()
        # move the files first
        ##12/19/17 commented out
        #if self.filemover_move.get()==1:
        #    print("files are still being moved from the detector server to ",self.filemover_target_dir.get())
        #    while self.filemover_move.get()==1:
        #        sleep(1)
        #    print("done.")
        #self.filemover_files.put(current_sample)
        #self.filemover_target_dir.put(data_path)        
        #self.filemover_move.put(1)
        ##12/19/17 commented out
        if self.parent.name == first_Pilatus() or self.parent.name == first_PilatusExt():
            release_lock()
        
    def get_frames_per_point(self):
        return self.parent.cam.num_images.get()   # always return 1 before 2018

class LIXPilatus(SingleTrigger, PilatusDetector):
    # this does not get root is input because it is hardcoded above
    file = Cpt(PilatusFilePlugin, suffix="cam1:",
               write_path_template="", reg=db.reg)

    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')

    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    stats4 = Cpt(StatsPlugin, 'Stats4:')

    reset_file_number = Cpt(Signal, name='reset_file_number', value=1)
    HeaderString = Cpt(EpicsSignal, "cam1:HeaderString")
    
    def __init__(self, *args, detector_id, **kwargs):
        self.detector_id = detector_id
        self._num_images = 1
        super().__init__(*args, **kwargs)

    def set_num_images(self, num_images):
        self._num_images = num_images
        
    def stage(self):
        self.cam.num_images.put(self._num_images)
        super().stage()
    
    def unstage(self):
        self.cam.num_images.put(1, wait=True)
        super().unstage()
        

############## below is based on code written by Bruno
############## hardware triggering for Pilatus detectors

class PilatusExtTrigger(PilatusDetector):
    armed = Cpt(EpicsSignal, "cam1:Armed")
    
    # Use self._image_name as in SingleTrigger?
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._num_images = 1
        self._acquisition_signal = self.cam.acquire
        self._counter_signal = self.cam.array_counter
        self._trigger_signal = EpicsSignal('XF:16ID-TS{EVR:C1-Out:FP3}Src:Scale-SP')
        
        self._status = None
        self.first = True
        self.acq_t = 0 
        
    def set_num_images(self, num_images):
        self._num_images = num_images
        
    def stage(self):
        print(self.name, "staging")
        self.stage_sigs.update([
            ('cam.trigger_mode', 3), # 2 DOESN'T WORK!
            ('cam.num_images', self._num_images)
        ])
        print(self.name, "stage sigs updated")
        super().stage()
        print(self.name, "super staged")
        self._counter_signal.put(0)
        acq_t = self.cam.acquire_period.get()
        if acq_t>0.1: 
            self.trig_width = 0.05
        else:
            self.trig_width = acq_t/2
        self.trig_wait = acq_t+0.02-self.trig_width
        #self._acquisition_signal.put(1) #, wait=True)
        print(self.name, "checking armed status")
        self._acquisition_signal.put(1) #, wait=True)
        while self.armed.get() != 1:
            time.sleep(0.5)
        
        print(self.name, "staged")
        
    def unstage(self):
        self._status = None
        self._acquisition_signal.put(0)
        self.cam.trigger_mode.put(0, wait=True)
        self.cam.num_images.put(1, wait=True)
        super().unstage()
        
    def trigger(self):
        print(self.name+" trigger")
        if self._staged != Staged.yes:
            raise RuntimeError("This detector is not ready to trigger."
                               "Call the stage() method before triggering.")
        
        status = DeviceStatus(self)
        # Only one Pilatus has to send the trigger
        if self.name == first_PilatusExt():
            print("triggering")
            self._trigger_signal.put(4, wait=True) # Force High
            time.sleep(self.trig_width)
            self._trigger_signal.put(3, wait=True) # Force Low          
        
        #set up callback to clear status after the end-of-exposure
        Timer(self.trig_wait, status._finished, ()).start()
            
        return status
        

class LIXPilatusExt(PilatusExtTrigger):
    file = Cpt(PilatusFilePlugin, suffix="cam1:",
               write_path_template="", reg=db.reg)

    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')

    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    stats4 = Cpt(StatsPlugin, 'Stats4:')

    reset_file_number = Cpt(Signal, name='reset_file_number', value=1)
    HeaderString = Cpt(EpicsSignal, "cam1:HeaderString")   # was missing before 2018

    def __init__(self, *args, **kwargs):
        self.detector_id = kwargs.pop('detector_id')
        super().__init__(*args, **kwargs)
        
        
pil1M = LIXPilatus("XF:16IDC-DT{Det:SAXS}", name="pil1M", detector_id="SAXS")
pilW1 = LIXPilatus("XF:16IDC-DT{Det:WAXS1}", name="pilW1", detector_id="WAXS1")
pilW2 = LIXPilatus("XF:16IDC-DT{Det:WAXS2}", name="pilW2", detector_id="WAXS2")

pil1M_ext = LIXPilatusExt("XF:16IDC-DT{Det:SAXS}", name="pil1M_ext", detector_id="SAXS")
pilW1_ext = LIXPilatusExt("XF:16IDC-DT{Det:WAXS1}", name="pilW1_ext", detector_id="WAXS1")
pilW2_ext = LIXPilatusExt("XF:16IDC-DT{Det:WAXS2}", name="pilW2_ext", detector_id="WAXS2")

pilatus_detectors = [pil1M, pilW1, pilW2]
pilatus_detectors_ext = [pil1M_ext, pilW1_ext, pilW2_ext]

for det in pilatus_detectors+pilatus_detectors_ext:
    det.read_attrs = ['file']

#def pilatus_set_Nimage(n):
#    for det in pilatus_detectors:
#        det.cam.num_images.put(n)
        
def pilatus_number_reset(status):
    for det in pilatus_detectors:
        val = 1 if status else 0
        det.reset_file_number.put(val)

def pilatus_ct_time(exp):
    for det in pilatus_detectors:
        det.cam.acquire_time.put(exp)
        det.cam.acquire_period.put(exp+0.01)        
        
def set_pil_num_images(num):
    for d in pilatus_detectors+pilatus_detectors_ext:
        d.set_num_images(num)




