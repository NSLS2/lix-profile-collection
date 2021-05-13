from ophyd import (SingleTrigger, MultiTrigger, TIFFPlugin,
                   ImagePlugin, StatsPlugin, TransformPlugin, DetectorBase, HDF5Plugin,
                   ROIPlugin, OverlayPlugin, ProcessPlugin, AreaDetector)

import ophyd.areadetector.cam as cam

from ophyd.areadetector.filestore_mixins import (FileStoreTIFFIterativeWrite,
                                                 FileStoreHDF5IterativeWrite)

from ophyd import Component as Cpt
import imageio,time,PIL,pyzbar
from pyzbar.pyzbar import decode

class TIFFPluginWithFileStore(TIFFPlugin, FileStoreTIFFIterativeWrite):
    def make_filename(self):
        global current_sample
        fname, read_path, write_path = super().make_filename()
        fname = self.parent.name + "_" + current_sample
        return fname, read_path, write_path

    def stage(self):
        global data_path
        rpath = f"{data_path}/tif/"
        makedirs(rpath, mode=0o0777)
        self.write_path_template = rpath
        super().stage()


class StandardProsilica(SingleTrigger, DetectorBase):
    _html_docs = ['prosilicaDoc.html']
    cam = Cpt(cam.ProsilicaDetectorCam, '')
    tiff = Cpt(TIFFPluginWithFileStore,
               suffix='TIFF1:',
               write_path_template='/nsls2/xf16id1/data/',   # this is updated when the plug in is staged
               ) #reg=db.reg)
    image = Cpt(ImagePlugin, 'image1:')
    trans = Cpt(TransformPlugin, 'Trans1:')
    over = Cpt(OverlayPlugin, 'Over1:')
    proc = Cpt(ProcessPlugin, 'Proc1:')
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')
    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._exp_completed = 0
        self.watch_timeouts_limit = 3
        self.watch_timeouts = 0
        self.watch_list = {}

    def _acquire_changed(self, value=None, old_value=None, **kwargs):
        if old_value==1 and value==0:
            self._status._finished()    
        
    def stage(self):  
        # when using as a detector, some parameters need to be set correctly
        self.stage_sigs[self.cam.image_mode] = 'Single'
        self.stage_sigs[self.cam.trigger_mode] = 'Fixed Rate'
        if hasattr(self, 'tiff'):
            self.stage_sigs[self.tiff.enable] = True

        super().stage()
        self._acquisition_signal.subscribe(self._acquire_changed)


    def unstage(self):
        #if hasattr(self, 'tiff'):
        #    self.tiff.enable.put(0, wait=True)
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

    def readQR(self, roi=1):
        d = self.snapshot(ROIs=[self.getROI(roi)])[0]
        im = PIL.Image.fromarray(d)
        ret = [c.data.decode() for c in decode(im)]
        return ret

    def saveImg(self, fn):
        size_x,size_y = self.cam.size.get()
        d = self.snapshot(ROIs=[[0, size_x, 0, size_y]])[0]
        imageio.imwrite(fn, d)    
    
    def setup_watch(self, watch_list):
        """ watch list is actually a dictionary
            the keys are the name of signals to watch, e.g. 
            the values are the threhsolds beyond which a change is deemed to be observed
        """
        self.watch_list = {}
        for sig_name in watch_list.keys():
            if not sig_name in self.read_attrs:
                raise Exception(f"{sig_name} is not a valid signal for {self.name}")
            sig = getattr(self, sig_name)
            self.watch_list[sig_name] = {'signal': sig, 
                                         'base_value': sig.get(), 
                                         'thresh': watch_list[sig_name]}
    
    def watch_for_change(self, lock=None, poll_rate=0.01, timeout=10):
        """ lock should have been acquired before this function is called
            when a change is observed, release the lock and return
        """
        if len(self.watch_list.keys())==0:
            print("nothing to watch for ...")
            return
        t1 = time.time()
        while True:
            changed = False
            for sig_name,sig in self.watch_list.items():
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
            lock.release()

def setup_cam(pv, name):
    try: 
        cam = StandardProsilica(pv, name=name)
    except TimeoutError:
        cam = None
        print("%s is not accessible." % name)

    cam.read_attrs = ['image', 'stats1', 'stats2', 'stats3', 'roi1', 'over', 'trans']
    cam.image.read_attrs = [] #'array_data']
    cam.stats1.read_attrs = ['total', 'centroid', 'profile_average']
    cam.stats2.read_attrs = ['total', 'centroid']
    cam.stats3.read_attrs = ['total', 'centroid']
    cam.stats1.centroid.read_attrs=['x','y']
    cam.stats1.profile_average.read_attrs=['x','y']
    cam.roi1.read_attrs = ['min_xyz', 'size']
    cam.tiff.read_attrs = [] # we dont need anything other than the image
    cam.over.read_attrs = [] # we dont need anything from overlay

    return cam

"""
camMono      = setup_cam("XF:16IDA-BI{Cam:Mono}", "camMono")
camKB        = setup_cam("XF:16IDA-BI{Cam:KB}", "camKB")

camFixedAper = setup_cam("XF:16IDA-BI{Cam:FixedApt}", "camFixedAper")    
camWBM       = setup_cam("XF:16IDA-BI{Cam:WBM}", "camWBM")

camKB        = setup_cam("XF:16IDA-BI{Cam:KB}", "camKB")
camSS        = setup_cam("XF:16IDB-BI{Cam:SS}", "camSS")
camAltSS     = setup_cam("XF:16IDB-BI{AltSS}", "camAltSS")  # should change the PV name from AltSS to Cam:AltSS

camBHutch    = setup_cam("XF:16IDB-BI{Cam:BHutch}", "camBHutch")
camSF        = setup_cam("XF:16IDC-BI{Cam:SF}", "camSF")
camSol        = setup_cam("XF:16IDC-BI{Cam:Sol}", "camSol")
camTop       = setup_cam("XF:16IDC-BI{Cam:sam_top}", "camTop")
#camOAM       = setup_cam("XF:16IDA-BI{Cam:OAM}", "camOAM")

camSampleTV  = setup_cam("XF:16IDC-BI{Cam:sam_top}", "camSampleTV")
camOAM       = setup_cam("XF:16IDA-BI{Cam:OAM}", "camOAM")
camSpare     = setup_cam("XF:16IDC-BI{Cam:Spare}", "camSpare")
camScope     = setup_cam("XF:16IDC-BI{Cam:Stereo}", "camScope") 
"""
