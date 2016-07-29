from ophyd import (SingleTrigger, TIFFPlugin, 
                   ImagePlugin, StatsPlugin, DetectorBase, HDF5Plugin,
                   ROIPlugin, AreaDetector)

import ophyd.areadetector.cam as cam

from ophyd.areadetector.filestore_mixins import (FileStoreTIFFIterativeWrite,
                                                 FileStoreHDF5IterativeWrite)

from ophyd import Component as Cpt

class TIFFPluginWithFileStore(TIFFPlugin, FileStoreTIFFIterativeWrite):
    pass

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

cam02 = StandardProsilica("XF:16IDA-BI{FS:2-Cam:1}", name="cam02")
cam03 = StandardProsilica("XF:16IDA-BI{FS:3-Cam:1}", name="cam03")
cam04 = StandardProsilica("XF:16IDA-BI{FS:4-Cam:1}", name="cam04")
cam05 = StandardProsilica("XF:16IDB-BI{FS:5-Cam:1}", name="cam05")
cam06 = StandardProsilica("XF:16IDC-ES:InAir{Mscp:1-Cam:1}", name="cam06")

all_standard_pros = [cam02, cam03, cam04, cam05, cam06]
for camera in all_standard_pros:
    camera.read_attrs= ['stats1', 'stats2','stats3'] #, 'tiff']
    camera.stats1.read_attrs = ['total', 'centroid']
    camera.stats2.read_attrs = ['total', 'centroid']
    camera.stats3.read_attrs = ['total', 'centroid']
    #camera.tiff.read_attrs = [] # we dont need anything other than the image

