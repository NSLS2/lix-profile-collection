from ophyd.areadetector.detectors import ProsilicaDetector
from ophyd.areadetector.plugins import ImagePlugin_V34 as ImagePlugin
from ophyd.areadetector.plugins import TIFFPlugin_V34 as TIFFPlugin
from ophyd.areadetector.plugins import TransformPlugin_V34 as TransformPlugin
from ophyd.areadetector.plugins import StatsPlugin_V34 as StatsPlugin
from ophyd.areadetector.plugins import ROIPlugin_V34 as ROIPlugin
from ophyd.areadetector.plugins import OverlayPlugin_V34 as OverlayPlugin
from ophyd.areadetector.plugins import ProcessPlugin_V34 as ProcessPlugin
from ophyd.areadetector.plugins import PvaPlugin
from ophyd.areadetector.trigger_mixins import SingleTrigger

from ophyd.areadetector.filestore_mixins import (FileStoreTIFFIterativeWrite,
                                                 FileStoreHDF5IterativeWrite)
from ophyd import Component as Cpt
import imageio,time

class TIFFPluginWithFileStore(TIFFPlugin, FileStoreTIFFIterativeWrite):
    def make_filename(self):
        global current_sample
        fname, read_path, write_path = super().make_filename()
        fname = self.parent.name + "_" + current_sample
        return fname, read_path, write_path

    def stage(self):
        global proposal_id, run_id, current_cycle, current_sample
        rpath = f"{get_IOC_datapath(self.parent.name)}/{current_sample}"
        self.write_path_template = rpath
        self.create_directory.put(-6)  # create up to 6 levels: ioc, cycle, pid, rid, ???, ??
        super().stage()    

class StandardProsilica(ProsilicaDetector, SingleTrigger):  
    # cam is defined in ProsilicaDetector
    image = Cpt(ImagePlugin, 'image1:')
    pva = Cpt(PvaPlugin, 'PVA1')
    trans = Cpt(TransformPlugin, 'Trans1:')
    over = Cpt(OverlayPlugin, 'Over1:')
    proc = Cpt(ProcessPlugin, 'Proc1:')
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    #roi2 = Cpt(ROIPlugin, 'ROI2:')
    #roi3 = Cpt(ROIPlugin, 'ROI3:')
    #roi4 = Cpt(ROIPlugin, 'ROI4:')
    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    tiff = Cpt(TIFFPluginWithFileStore,
               suffix='TIFF1:',
               write_path_template='/nsls2/xf16id1/data/',   # this is updated when the plugin is staged
               ) 
   
    def __init__(self, *args, detector_id=None, **kwargs): 
        self._exp_completed = 0
        self.watch_timeouts_limit = 3
        self.watch_timeouts = 0
        self.watch_list = {}
        if detector_id:
            self.detector_id = detector_id
        else:
            self.detector_id = "unknown"
        super().__init__(*args, **kwargs)

    def make_data_key(self):
        ret = super().make_data_key()
        color_mode = self.cam.color_mode.get(as_string=True)
        if color_mode == 'Mono':
            ret['shape'] = [
                # TODO paramaterize this better
                1,
                self.tiff.array_size.height.get(),
                self.tiff.array_size.width.get()
                ]
            ret['dims'] = ['frame', 'y', 'x']
        else:
            ret['shape'] = [
                # this seems screwed up:
                # In [8]: camES1.tiff.array_size.get()
                # Out[8]: ArraySizeTuple(depth=1200, height=1600, width=3)
                1,
                self.tiff.array_size.depth.get(),
                self.tiff.array_size.height.get(),
                self.tiff.array_size.width.get()
                ]
            ret['dims'] = ['frame', 'y', 'x', 'z']

        cam_dtype = self.cam.data_type.get(as_string=True)
        type_map = {'UInt8': '|u1', 'UInt16': '<u2', 'Float32':'<f4', "Float64":'<f8', 'Int8': '<i4'}
        if cam_dtype in type_map:
            ret['dtype_str'] = type_map[cam_dtype]
        return ret
  
    def _acquire_changed(self, value=None, old_value=None, **kwargs):
        if old_value==1 and value==0:
            self._status._finished()    
        
    def stage(self):  
        # when using as a detector, some parameters need to be set correctly
        if data_path=="" and "tiff" in self.read_attrs:
            raise Exception("data_path is empty, login() first.")
        self.stage_sigs[self.cam.image_mode] = 'Single'
        self.stage_sigs[self.cam.trigger_mode] = 'Fixed Rate'
        if hasattr(self, 'tiff'):
            self.stage_sigs[self.tiff.enable] = True

        super().stage()
        self._acquisition_signal.subscribe(self._acquire_changed)


    def unstage(self):
        if hasattr(self, 'tiff'):
            self.tiff.enable.put(0, wait=True)
        self._acquisition_signal.clear_sub(self._acquire_changed)
        super().unstage()
 
    
    def trigger(self):
        if self._staged != Staged.yes:
            raise RuntimeError("This detector is not ready to trigger."
                               "Call the stage() method before triggering.")

        self._status = DeviceStatus(self) # self._status_type(self)
        self._acquisition_signal.put(1, wait=False)
        time.sleep(self.cam.acquire_period.get())
        #self.cam.trigger_software.put(1, wait=False)
        #threading.Timer(self.cam.acquire_period.get(), self._status._finished, ()).start()
        self.dispatch(self._image_name, ttime.time())
        return self._status
        

    # ROIs = [ROI1, ROI2, ...]
    # each ROI is defined as [startX, sizeX, startY, sizeY]
    def setROI(self,i,ROI):
        if i>0 and i<=4:
            caput(self.prefix+("ROI%d:MinX" % i), ROI[0]) 
            caput(self.prefix+("ROI%d:SizeX" % i), ROI[1]) 
            caput(self.prefix+("ROI%d:MinY" % i), ROI[2]) 
            caput(self.prefix+("ROI%d:SizeY" % i), ROI[3])
        else:
            raise(ValueError("valid ROI numbers are 1-4"))
            
    def getROI(self,i):
        ROIs = {1: self.roi1, 2: self.roi2, 3:self.roi3, 4:self.roi4}
        if i>0 and i<=4:
            print("%s: [%d, %d, %d, %d]" % (ROIs[i].name,
                                           ROIs[i].min_xyz.min_x.get(),
                                           ROIs[i].size.x.get(),
                                           ROIs[i].min_xyz.min_y.get(),
                                           ROIs[i].size.y.get()))
            return [ROIs[i].min_xyz.min_x.get(),
                    ROIs[i].size.x.get(),
                    ROIs[i].min_xyz.min_y.get(),
                    ROIs[i].size.y.get()]
        else:
            raise(ValueError("valid ROI numbers are 1-4"))       
    
    def snapshot(self,showWholeImage=False, ROIs=None, showROI=False, retry=3):
        # array_data.value may have different shapes (mono/Bayer vs RGB)\
        for i in range(retry):
            img = np.asarray(self.image.array_data.get())
            if len(img)>0:
                break
            if i==retry-1:
                return None
        
        if self.image.array_size.depth.get()>0:  # RGB
            img = img.reshape([self.image.array_size.depth.get(),
                               self.image.array_size.height.get(),
                               self.image.array_size.width.get()])
        else: # mono/Bayer
            img = img.reshape([self.image.array_size.height.get(),
                               self.image.array_size.width.get()])
        # demosaic first
        if showWholeImage:
            plt.figure()
            plt.imshow(img)
            plt.show()

        # show ROIs
        if ROIs is None: 
            return
        # ROI definition: [MinX, SizeX, MinY, SizeY]
        n = len(ROIs)
        data = []
        for i in range(n):
            roi = img[ROIs[i][2]:ROIs[i][2]+ROIs[i][3],ROIs[i][0]:ROIs[i][0]+ROIs[i][1]]
            data.append(roi)
            if showROI:
                if i==0:
                    plt.figure()
                plt.subplot(1,n,i+1)
                plt.imshow(roi)
                if i==n-1: 
                    plt.show()

        return(data)

    def saveImg(self, fn):
        size_x,size_y = self.cam.size.get()
        d = self.snapshot(ROIs=[[0, size_x, 0, size_y]])[0]
        imageio.imwrite(fn, d)    


    def setup_watch(self, watch_name, sig_name, threshold, base_value=None):
        """ watch list is actually a dictionary
            the keys are the name of signals to watch, e.g. 
            the values are the threhsolds beyond which a change is deemed to be observed
        """
        if not sig_name in self.read_attrs:
            raise Exception(f"{sig_name} is not a valid signal for {self.name}")
        sig = getattr(self, sig_name)
        if base_value is None:
            base_value = sig.get()
        self.watch_list[watch_name] = {'signal': sig, 'base_value': base_value, 'thresh': threshold}
    
    def watch_for_change(self, lock=None, poll_rate=0.01, timeout=10, watch_name=None, release_delay=0):
        """ lock should have been acquired before this function is called
            when a change is observed, release the lock and return
        """
        if len(self.watch_list.keys())==0:
            print("nothing to watch for ...")
            return
        t1 = time.time()
        while True:
            changed = False
            if watch_name is None:
                watch_name = list(self.watch_list.keys())
            elif isinstance(watch_name, str):
                watch_name = [watch_name]
            for wn in watch_name:
                sig = self.watch_list[wn]
                cur_value = sig['signal'].get()
                if abs(cur_value-sig['base_value'])>sig['thresh']:
                    print('change detected.')
                    changed = True
            if changed:
                self.watch_timeouts=0
                break
            t2 = time.time()
            if t2-t1>timeout:
                self.watch_timeouts+=1
                print(f'timedout #{self.watch_timeouts}')
                if self.watch_timeouts>=self.watch_timeouts_limit:
                    raise Exception(f"max # of timeouts reached.")
                break
            time.sleep(poll_rate)
        if lock is not None:
            time.sleep(release_delay)
            lock.release()

known_cameras = {"camMono": "XF:16IDA-BI{Cam:Mono}",
                 "camKB": "XF:16IDA-BI{Cam:KB}",
                 "camFixedAper": "XF:16IDA-BI{Cam:FixedApt}",
                 "camWBM": "XF:16IDA-BI{Cam:WBM}",
                 "camKB": "XF:16IDA-BI{Cam:KB}",
                 "camSS": "XF:16IDB-BI{Cam:SS}",
                 "camBHutch": "XF:16IDB-BI{Cam:BHutch}",
                 "camSF": "XF:16IDC-BI{Cam:SF}",
                 "camES1": "XF:16IDC-BI{Cam:es1}",
                 "camES2": "XF:16IDC-BI{Cam:es2}",
                 "camTop": "XF:16IDC-BI{Cam:sam_top}",
                 "camScope": "XF:16IDC-BI{Cam:Stereo}", 
                }

#camOAM       = setup_cam("XF:16IDA-BI{Cam:OAM}", "camOAM")
            
def setup_cam(name):
    if not name in known_cameras.keys():
        raise Exception(f"{name} is not a known camera.")
    pv = known_cameras[name]
    try: 
        cam = StandardProsilica(pv, name=name)
    except TimeoutError:
        cam = None
        print("%s is not accessible." % name)

    cam.read_attrs = ['tiff', 'stats1', 'stats2', 'stats3', 'roi1']
    #cam.image.read_attrs = [] #'array_data']
    cam.stats1.read_attrs = ['total', 'centroid', 'profile_average']
    cam.stats2.read_attrs = ['total', 'centroid']
    cam.stats3.read_attrs = ['total', 'centroid']
    cam.stats1.centroid.read_attrs=['x','y']
    cam.stats1.profile_average.read_attrs=['x','y']
    cam.roi1.read_attrs = ['min_xyz', 'size']
    cam.tiff.read_attrs = [] # we dont need anything other than the image
    #cam.over.read_attrs = [] # we dont need anything from overlay

    return cam

## beam visualization screens
class Screen(Device):
    y=Cpt(EpicsMotor, '-Ax:Y}Mtr')
    
    def __init__(self, pos_dict, *args, cam_name=None, **kwargs):
        if cam_name is not None:
            self.cam = setup_cam(cam_name)
        self.pos_dict = pos_dict
        super().__init__(*args, **kwargs)

    def mov(self, pos):
        if not pos in list(self.pos_dict.keys()):
            raise Exception(f"{pos} is not an known location.")
        self.y.mov(self.pos_dict[pos])
        
scnMono = Screen('XF:16IDA-BI{FS:3-Ax:Y}Mtr', {},
                 cam_name="camMono", name='scnMono')
scnKB = Screen('XF:16IDA-BI{FS:4-Ax:Y}Mtr', {}, 
               cam_name="camKB", name='scnKB')
scnSS = Screen('XF:16IDB-BI{SCN:SS', {}, 
               cam_name="camSS",  name='scnSS')
scnSF = Screen('XF:16IDC-BI{FS:SF', {}, 
               cam_name="camSF",  name='scnSF')


