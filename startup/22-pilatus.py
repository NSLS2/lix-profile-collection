from ophyd import ( Component as Cpt, ADComponent,
                    EpicsSignal, EpicsSignalRO,
                    ROIPlugin, StatsPlugin, ImagePlugin,
                    SingleTrigger, PilatusDetector)

from ophyd.areadetector.filestore_mixins import FileStoreBulkWrite

from ophyd.utils import set_and_wait
from filestore.handlers_base import PilatusCBFHandler
import filestore.api as fs
<<<<<<< HEAD
import fabio
import os,time,threading
=======
import os
>>>>>>> f6cd9319bc2f1bb0f7f9aceb32be59ca260f49cf


def first_Pilatus():
    #print("checking first Pialtus")
    for det in gs.DETS:
        if det.__class__ == LIXPilatus:
            #print(det.name)
            return det.name
    return None

def first_PilatusExt():
    #print("checking first Pialtus")
    for det in gs.DETS:
        if det.__class__ == LIXPilatusExt:
            #print(det.name)
            return det.name
    return None

class PilatusFilePlugin(Device, FileStoreBulkWrite):
    file_path = ADComponent(EpicsSignalWithRBV, 'FilePath', string=True)
    file_number = ADComponent(EpicsSignalWithRBV, 'FileNumber')
    file_name = ADComponent(EpicsSignalWithRBV, 'FileName', string=True)
    file_template = ADComponent(EpicsSignalWithRBV, 'FileTemplate', string=True)
    file_header = Cpt(Signal, name='HeaderString')
    reset_file_number = Cpt(Signal, name='reset_file_number', value=1)
    filemover_files = Cpt(EpicsSignal, 'filemover.filename')
    filemover_target_dir = Cpt(EpicsSignal, 'filemover.target')
    filemover_move = Cpt(EpicsSignal, 'filemover.moving')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._datum_kwargs_map = dict()  # store kwargs for each uid

    def stage(self):
        global proposal_id
        global run_id
        global current_sample
        global data_path
        
        set_and_wait(self.file_template, '%s%s_%6.6d_'+self.parent.detector_id+'.cbf', timeout=99999)
        if self.reset_file_number.get() == 1:
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
<<<<<<< HEAD
        
        set_and_wait(self.file_path, "/ramdisk/", timeout=99999)
        #set_and_wait(self.file_path, data_path, timeout=99999)
        set_and_wait(self.file_name, current_sample, timeout=99999)
        #self.file_header.put("uid=%s" % )
        
=======

        #set_and_wait(self.file_path, "/ramdisk/", timeout=99999)
        set_and_wait(self.file_path, data_path, timeout=99999)
        set_and_wait(self.file_name, current_sample, timeout=99999)

>>>>>>> f6cd9319bc2f1bb0f7f9aceb32be59ca260f49cf
        super().stage()
        res_kwargs = {'template': self.file_template.get(),
                      'filename': self.file_name.get(),
                      'frame_per_point': self.get_frames_per_point(),
                      'initial_number': self.file_number.get()}
        #self._resource = fs.insert_resource('AD_CBF', rpath, res_kwargs, root=path)
        self._resource = fs.insert_resource('AD_CBF', data_path, res_kwargs, root="/")
<<<<<<< HEAD
       
        try: # this is used by solution scattering only
            sol
        except NameError:
            pass
        else:
            if self.parent.name == first_Pilatus():
                caput("XF:16IDC-ES:Sol{ctrl}ready", 1)
=======

        if self.parent.name == first_Pilatus():
            caput("XF:16IDC-ES:Sol{ctrl}ready", 1)
>>>>>>> f6cd9319bc2f1bb0f7f9aceb32be59ca260f49cf

    def unstage(self):
        super().unstage()
<<<<<<< HEAD
        # move the files first
        if self.filemover_move.get()==1:
            print("files are still being moved from the detector server to ",self.filemover_target_dir.get())
            while self.filemover_move.get()==1:
                sleep(1)
            print("done.")
        self.filemover_files.put(current_sample)
        self.filemover_target_dir.put(data_path)        
        self.filemover_move.put(1)

        if self.parent.name == first_Pilatus() or self.parent.name == first_PilatusExt():
            release_lock()
        
    def get_frames_per_point(self):
        return 1

class PilatusCBFHandler(HandlerBase):
    specs = {'AD_CBF'} | HandlerBase.specs

    def __init__(self, rpath, template, filename, frame_per_point=1, initial_number=1):
        self._path = rpath
        self._fpp = frame_per_point
        self._template = template
        self._filename = filename
        self._initial_number = initial_number

    def __call__(self, point_number):
        start, stop = self._initial_number + point_number * self._fpp, (point_number + 2) * self._fpp
        ret = []
        # commented out by LY to test scan speed imperovement, 2017-01-24
        for j in range(start, stop):
            fn = self._template % (self._path, self._filename, j)
            #print("call Open File: ", fn)
            img = fabio.open(fn)
            ret.append(img.data)
        return np.array(ret).squeeze()

    def get_file_list(self, datum_kwargs_gen):
        file_list = []
        for dk in datum_kwargs_gen:
            point_number = dk['point_number']
            start, stop = self._initial_number + point_number * self._fpp, (point_number + 2) * self._fpp
            ret = []
            for j in range(start, stop):
                fn = self._template % (self._path, self._filename, j)
                #print("Will open file: ", fn)
                file_list.append(fn)
        return file_list
=======
        #if self.parent.name == first_Pilatus():
        #    release_lock()

    def get_frames_per_point(self):
        return 1

>>>>>>> f6cd9319bc2f1bb0f7f9aceb32be59ca260f49cf

class LIXPilatus(SingleTrigger, PilatusDetector):
    # this does not get root is input because it is hardcoded above
    file = Cpt(PilatusFilePlugin, suffix="cam1:",
               write_path_template="",
               fs=db.fs)

    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')

    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    stats4 = Cpt(StatsPlugin, 'Stats4:')

<<<<<<< HEAD
    HeaderString = Cpt(EpicsSignal, "cam1:HeaderString")
    
    def __init__(self, *args, **kwargs):
        self.detector_id = kwargs.pop('detector_id')
=======
    def __init__(self, *args, detector_id, **kwargs):
        self.detector_id = detector_id
>>>>>>> f6cd9319bc2f1bb0f7f9aceb32be59ca260f49cf
        super().__init__(*args, **kwargs)

pil1M = LIXPilatus("XF:16IDC-DT{Det:SAXS}", name="pil1M", detector_id="SAXS")
pilW1 = LIXPilatus("XF:16IDC-DT{Det:WAXS1}", name="pilW1", detector_id="WAXS1")
pilW2 = LIXPilatus("XF:16IDC-DT{Det:WAXS2}", name="pilW2", detector_id="WAXS2")

pilatus_detectors = [pil1M, pilW1, pilW2]

for det in pilatus_detectors:
   det.read_attrs = ['file']

def pilatus_set_Nimage(n):
    for det in pilatus_detectors:
        det.cam.num_images.put(n)
    #pil1M.cam.num_images.put(n)
    #pilW1.cam.num_images.put(n)
    #pilW2.cam.num_images.put(n)
        
def pilatus_number_reset(status):
    for det in pilatus_detectors:
        val = 1 if status else 0
        det.file.reset_file_number.put(val)


def pilatus_ct_time(exp):
    for det in pilatus_detectors:
        det.cam.acquire_time.put(exp)
        det.cam.acquire_period.put(exp+0.01)
    #pil1M.cam.acquire_time.put(exp)
    #pilW1.cam.acquire_time.put(exp)
    #pilW2.cam.acquire_time.put(exp)
    #pil1M.cam.acquire_period.put(exp+0.01)
    #pilW1.cam.acquire_period.put(exp+0.01)
    #pilW2.cam.acquire_period.put(exp+0.01)

<<<<<<< HEAD
try:
    db.fs.register_handler('AD_CBF', PilatusCBFHandler)
except:
    pass

=======

db.fs.register_handler('AD_CBF', PilatusCBFHandler)


pil1M = LIXPilatus("XF:16IDC-DT{Det:SAXS}", name="pil1M", detector_id="SAXS")
pilW1 = LIXPilatus("XF:16IDC-DT{Det:WAXS1}", name="pilW1", detector_id="WAXS1")
pilW2 = LIXPilatus("XF:16IDC-DT{Det:WAXS2}", name="pilW2", detector_id="WAXS2")
>>>>>>> f6cd9319bc2f1bb0f7f9aceb32be59ca260f49cf

############## below is based on code written by Bruno
############## hardware triggering for Pilatus detectors

class PilatusExtTrigger(PilatusDetector):
    # Use self._image_name as in SingleTrigger?
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #self.stage_sigs.update([
        #    ('cam.trigger_mode', 2), # Ext. Triggrer; 3 in Bruno's original code, Mult. Trigger
        #])
        self._num_images = 1
        self._acquisition_signal = self.cam.acquire
        self._counter_signal = self.cam.array_counter
        self._trigger_signal = EpicsSignal('XF:16ID-TS{EVR:C1-Out:FP3}Src:Scale-SP')
        
        self._status = None
        self.first = True
        
    def set_num_images(self, num_images):
        self._num_images = num_images
        
    def stage(self):
        print(self.name, "stage")
        self.stage_sigs.update([
            ('cam.trigger_mode', 2),
            ('cam.num_images', self._num_images)
        ])
        super().stage()
        print(self.name, "after super().stage()")
        self._counter_signal.subscribe(self._counter_changed)
        print(self.name, "subscribed to counter signal")
        self._acquisition_signal.put(1) #, wait=True)
        print(self.name, "acquisition=1")
        self.first = True
        
    def unstage(self):
        self._counter_signal.clear_sub(self._counter_changed)
        self._status = None
        self._acquisition_signal.put(0)
        self.cam.trigger_mode.put(0, wait=True)
        super().unstage()
        
    def do_trigger(self):
        print("sending trigger")
        if self.first:
            time.sleep(0.7)       # for some reason this delay is necesary, but only for the first trigger
            #self.first = False
        self._trigger_signal.put(4, wait=True) # Force High
        time.sleep(0.2)
        self._trigger_signal.put(3, wait=True) # Force Low
        print("sent trigger")
        
    def trigger(self):
        print(self.name+" trigger")
        if self._staged != Staged.yes:
            raise RuntimeError("This detector is not ready to trigger."
                               "Call the stage() method before triggering.")
        
        self._status = DeviceStatus(self)
        
        # Only one Pilatus has to send the trigger
        if self.name == first_PilatusExt():
        #if "pil1M" in self.name:
            threading.Thread(target=self.do_trigger).start()
            #self.do_trigger()
            
        return self._status
        
    def _counter_changed(self, value=None, old_value=None, **kwargs):
        if self._status is None:
            return
        
        if old_value + 1 == value:
            print(self.name + " finished")
            self._status._finished()
        else:
            print("Unexpected counter change from", old_value, "to", value)

class LIXPilatusExt(PilatusExtTrigger):
    file = Cpt(PilatusFilePlugin, suffix="cam1:",
               write_path_template="", fs=db.fs)

    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')

    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    stats4 = Cpt(StatsPlugin, 'Stats4:')

    def __init__(self, *args, **kwargs):
        self.detector_id = kwargs.pop('detector_id')
        super().__init__(*args, **kwargs)
        
pil1M_ext = LIXPilatusExt("XF:16IDC-DT{Det:SAXS}", name="pil1M_ext", detector_id="SAXS")
pilW1_ext = LIXPilatusExt("XF:16IDC-DT{Det:WAXS1}", name="pilW1_ext", detector_id="WAXS1")
pilW2_ext = LIXPilatusExt("XF:16IDC-DT{Det:WAXS2}", name="pilW2_ext", detector_id="WAXS2")

pilatus_detectors_ext = [pil1M_ext, pilW1_ext, pilW2_ext]

for det in pilatus_detectors_ext:
    det.read_attrs = ['file']

def set_pil_num_images(num):
    for d in pilatus_detectors_ext:
        d.set_num_images(num)


<<<<<<< HEAD


=======
for det in pilatus_detectors:
    det.read_attrs = ['file']
>>>>>>> f6cd9319bc2f1bb0f7f9aceb32be59ca260f49cf
