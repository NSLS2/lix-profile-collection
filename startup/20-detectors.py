from ophyd import (SingleTrigger, TIFFPlugin, 
                   ImagePlugin, StatsPlugin, DetectorBase, HDF5Plugin,
                   ROIPlugin, OverlayPlugin, AreaDetector)

import ophyd.areadetector.cam as cam

from ophyd.areadetector.filestore_mixins import (FileStoreTIFFIterativeWrite,
                                                 FileStoreHDF5IterativeWrite)

from ophyd import Component as Cpt
from scipy.misc import imsave

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

class LixProsilicaDetector(DetectorBase):
    _html_docs = ['prosilicaDoc.html']
    cam = Cpt(cam.ProsilicaDetectorCam, '')

class StandardProsilica(SingleTrigger, LixProsilicaDetector):
    #tiff = Cpt(TIFFPluginWithFileStore,
    #           suffix='TIFF1:',
    #           write_path_template='/GPFS/xf16id/data2/')
    image = Cpt(ImagePlugin, 'image1:')
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')
    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    stats4 = Cpt(StatsPlugin, 'Stats4:')
    stats5 = Cpt(StatsPlugin, 'Stats5:')

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
       
            
    def snapshot(self,showWholeImage=False, ROIs=None, showROI=False):
        # array_data.value may have different shapes (mono/Bayer vs RGB)\
        img = np.asarray(self.image.array_data.value)
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
        if ROIs==None: 
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
        imsave(fn, d)    

class StandardProsilicaWithTIFF(StandardProsilica):
    tiff = Cpt(TIFFPluginWithFileStore,
               suffix='TIFF1:',
               write_path_template='/GPFS/xf16id/exp_path/')


class LIXMicroscopeCamera(StandardProsilica):
    tiff = Cpt(TIFFPluginWithFileStore,
               suffix='TIFF1:',
               write_path_template='/GPFS/xf16id/exp_path/',
               fs=db.fs)

    over1 = Cpt(OverlayPlugin, 'Over1:')

def setup_cam(pv, name):
    try: 
        cam = StandardProsilica(pv, name=name)
    except TimeoutError:
        cam = None
        print("%s is not accessible." % name)
    
    return cam
    
def setup_camRGB(pv, name):
    try: 
        cam = LIXMicroscopeCamera(pv, name=name)
    except TimeoutError:
        cam = None
        print("%s is not accessible." % name)
    
    return cam
    
cam01 = setup_cam("XF:16IDA-BI{FS:1-Cam:1}", "cam01")
cam02 = setup_cam("XF:16IDA-BI{FS:2-Cam:1}", "cam02")
cam03 = setup_cam("XF:16IDA-BI{FS:3-Cam:1}", "cam03")
cam04 = setup_cam("XF:16IDA-BI{FS:4-Cam:1}", "cam04")
cam05 = setup_cam("XF:16IDB-BI{FS:5-Cam:1}", "cam05")
cam06 = setup_cam("XF:16IDB-BI{FS:6-Cam:1}", "cam05")

    
all_standard_pros = [cam01, cam02, cam03, cam04, cam05, cam06]

for camera in all_standard_pros:
    if camera!=None:
        camera.read_attrs= ['stats1', 'stats2','stats3'] #, 'tiff']
        camera.stats1.read_attrs = ['total', 'centroid']
        camera.stats2.read_attrs = ['total', 'centroid']
        camera.stats3.read_attrs = ['total', 'centroid']
        #camera.tiff.read_attrs = [] # we dont need anything other than the image
        
#cam_mic = setup_camRGB("XF:16IDC-ES:InAir{Mscp:1-Cam:1}", "cam_mic")
cam_sol = setup_camRGB("XF:16IDC-BI{Cam:Sol}", "cam_sol")
cam_overhead = setup_camRGB("XF:16IDC-BI{FS:9-Cam:1}", "cam_mic")
cam_spare = setup_camRGB("XF:16IDC-BI{Cam:Spare}", "cam_mic")
    
all_RGB_cam = [cam_sol, cam_overhead, cam_spare] #, cam_mic]
    
for cam in all_RGB_cam:
    if cam!=None:
        cam.read_attrs = ['stats1', 'stats2', 'stats3', 'roi1', 'tiff']
        cam.stats1.read_attrs = ['total', 'centroid']
        cam.stats2.read_attrs = ['total', 'centroid']
        cam.stats3.read_attrs = ['total', 'centroid']
        cam.roi1.read_attrs = ['min_xyz', 'size']
        cam.tiff.read_attrs = [] # we dont need anything other than the image
        cam.over1.read_attrs = [] # we dont need anything from overlay

        ##### FIX while not corrected on Ophyd - ADBase - validate_asyn_port
        ##
        # In the case of the OverlayPlugin, the Overlay object has no port_name
        # which leads to a empty port_map at asyn_digraph.
        #
        for overlay in cam.over1.signal_names:
            if overlay.startswith('overlay'):
                getattr(cam.over1, overlay).validate_asyn_ports = lambda: None
