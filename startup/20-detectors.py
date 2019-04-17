from ophyd import (SingleTrigger, MultiTrigger, TIFFPlugin,
                   ImagePlugin, StatsPlugin, DetectorBase, HDF5Plugin,
                   ROIPlugin, OverlayPlugin, ProcessPlugin, AreaDetector)

import ophyd.areadetector.cam as cam

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
        global proposal_id
        global run_id
        path = '/GPFS/xf16id/exp_path/'
        rpath = str(proposal_id)+"/"+str(run_id)+"/"
        makedirs(path+rpath)
        self.write_path_template = path+rpath
        super().stage()


class StandardProsilica(SingleTrigger, DetectorBase):
    _html_docs = ['prosilicaDoc.html']
    cam = Cpt(cam.ProsilicaDetectorCam, '')
    tiff = Cpt(TIFFPluginWithFileStore,
               suffix='TIFF1:',
               write_path_template='/GPFS/xf16id/exp_path/',   # this is updated when the plug in is staged
               reg=db.reg)
    image = Cpt(ImagePlugin, 'image1:')
    over1 = Cpt(OverlayPlugin, 'Over1:')
    proc1 = Cpt(ProcessPlugin, 'Proc1:')
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')
    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')

    def stage(self):
        self.cam.acquire.put(0)
        super().stage()

    def unstage(self):
        if hasattr(self, 'tiff'):
            self.tiff.enable.put(0)
        super().unstage()
        
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
                                           ROIs[i].min_xyz.min_x.value,
                                           ROIs[i].size.x.value,
                                           ROIs[i].min_xyz.min_y.value,
                                           ROIs[i].size.y.value))
            return [ROIs[i].min_xyz.min_x.value,
                    ROIs[i].size.x.value,
                    ROIs[i].min_xyz.min_y.value,
                    ROIs[i].size.y.value]
        else:
            raise(ValueError("valid ROI numbers are 1-4"))       
            
    def snapshot(self,showWholeImage=False, ROIs=None, showROI=False, retry=3):
        # array_data.value may have different shapes (mono/Bayer vs RGB)\
        for i in range(retry):
            img = np.asarray(self.image.array_data.value)
            if len(img)>0:
                break
            if i==retry-1:
                return None
        
        if self.image.array_size.depth.get()>0:  # RGB
            img = img.reshape([self.image.array_size.depth.value,
                               self.image.array_size.height.value,
                               self.image.array_size.width.value])
        else: # mono/Bayer
            img = img.reshape([self.image.array_size.height.value,
                               self.image.array_size.width.value])
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
        
    def watch_for_change(self, max_thresh=0, sigma_thresh=0, lock=None, poll_rate=0.05, timeout=10):
        """ lock should have been acquired before this function is called
            when a change is observed, release the lock and return
        """
        t1 = time.time()
        while True:
            if self.stats1.max_value.get()>max_thresh and self.stats1.sigma.get()>sigma_thresh:
                break
            t2 = time.time()
            if t2-t1>timeout:
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

    cam.read_attrs = ['image', 'stats1', 'stats2', 'stats3', 'roi1']#, 'tiff']
    cam.image.read_attrs = ['array_data']
    cam.stats1.read_attrs = ['total', 'centroid', 'profile_average']
    cam.stats2.read_attrs = ['total', 'centroid']
    cam.stats3.read_attrs = ['total', 'centroid']
    cam.stats1.centroid.read_attrs=['x','y']
    cam.stats1.profile_average.read_attrs=['x','y']
    cam.roi1.read_attrs = ['min_xyz', 'size']
    #cam.tiff.read_attrs = [] # we dont need anything other than the image
    #cam.over1.read_attrs = [] # we dont need anything from overlay

    return cam

camMono      = setup_cam("XF:16IDA-BI{Cam:Mono}", "camMono")
camKB        = setup_cam("XF:16IDA-BI{Cam:KB}", "camKB")

camFixedAper = setup_cam("XF:16IDA-BI{Cam:FixedApt}", "camFixedAper")    
camWBM       = setup_cam("XF:16IDA-BI{Cam:WBM}", "camWBM")

camKB        = setup_cam("XF:16IDA-BI{Cam:KB}", "camKB")
camSS        = setup_cam("XF:16IDB-BI{Cam:SS}", "camSS")
camAltSS     = setup_cam("XF:16IDB-BI{AltSS}", "camAltSS")  # should change the PV name from AltSS to Cam:AltSS

camBHutch    = setup_cam("XF:16IDB-BI{Cam:BHutch}", "camBHutch")
camSF        = setup_cam("XF:16IDC-BI{Cam:SF}", "camSF")
"""
camSol       = setup_cam("XF:16IDC-BI{Cam:Sol}", "camSol")
camSampleTV  = setup_cam("XF:16IDC-BI{Cam:sam_top}", "camSampleTV")
camOAM       = setup_cam("XF:16IDA-BI{Cam:OAM}", "camOAM")
camSpare     = setup_cam("XF:16IDA-BI{Cam:Spare}", "camSpare")
camScope     = setup_cam("XF:16IDA-BI{Cam:Stereo}", "camScope") 
"""