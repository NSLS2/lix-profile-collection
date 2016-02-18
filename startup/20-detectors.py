from ophyd import (SingleTrigger, TIFFPlugin,
                   ImagePlugin, StatsPlugin, ROIPlugin, DetectorBase, HDF5Plugin,
                   AreaDetector)

import ophyd.areadetector.cam as cam

from ophyd.areadetector.filestore_mixins import (FileStoreTIFFIterativeWrite,
                                                 FileStoreHDF5IterativeWrite)

from ophyd import Component as Cpt

class LixProsilicaDetector(DetectorBase):
    _html_docs = ['prosilicaDoc.html']
    cam = Cpt(cam.ProsilicaDetectorCam, '')

class StandardProsilica(SingleTrigger, LixProsilicaDetector):
    #tiff = Cpt(TIFFPluginWithFileStore,
    #           suffix='TIFF1:',
    #           write_path_template='/XF16ID/data/')
    image = Cpt(ImagePlugin, 'image1:')
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')
    roi5 = Cpt(ROIPlugin, 'ROI5:')
    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    stats4 = Cpt(StatsPlugin, 'Stats4:')
    stats5 = Cpt(StatsPlugin, 'Stats5:')


cam04 = StandardProsilica("XF:16IDA-BI{FS:4-Cam:1}", name="cam04")
cam05 = StandardProsilica("XF:16IDB-BI{FS:5-Cam:1}", name="cam05")

all_standard_pros = [cam04, cam05]
for camera in all_standard_pros:
    camera.read_attrs = ['stats1', 'stats2','stats3','stats4','stats5']  #, 'tiff']
    #camera.tiff.read_attrs = []  # leaving just the 'image'
    camera.stats1.read_attrs = ['total', 'centroid']
    camera.stats2.read_attrs = ['total', 'centroid']
    camera.stats3.read_attrs = ['total', 'centroid']
    camera.stats4.read_attrs = ['total', 'centroid']
    camera.stats5.read_attrs = ['total', 'centroid']
