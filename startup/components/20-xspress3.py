print(f"Loading {__file__}...")

from ophyd.areadetector import Xspress3Detector
from nslsii.areadetector.xspress3 import build_xspress3_class,Xspress3HDF5Plugin,Xspress3Trigger
    
from ophyd.areadetector import (DetectorBase, CamBase,
                                EpicsSignalWithRBV as SignalWithRBV)
from ophyd import (Signal, EpicsSignal, EpicsSignalRO, DerivedSignal)

from ophyd import (Device, Component as Cpt, FormattedComponent as FC,
                   DynamicDeviceComponent as DDC)
from ophyd.areadetector.plugins import PluginBase
from ophyd.areadetector.filestore_mixins import FileStorePluginBase
from ophyd.areadetector.plugins import ImagePlugin,HDF5Plugin
from ophyd.areadetector import ADBase
from ophyd.device import (BlueskyInterface, Staged)
from ophyd.status import DeviceStatus

from collections import OrderedDict

"""
IMPORTANT:
Since the device is from the detector pool, there is no guarantee that all parameters are loaded 
correctly when the IOC starts. This particular one has caused persistent problem.

lyang@xf16id-ws3:xf16id1$ caput XF:16IDC-ES{Xsp:1}:ARR1:NDArrayPort XSP3
Old : XF:16IDC-ES{Xsp:1}:ARR1:NDArrayPort XSP3.ROI1
New : XF:16IDC-ES{Xsp:1}:ARR1:NDArrayPort XSP3

2023-10-20
atempting to use in fly scans and save data in hdf
hdf plugin array port: originally XSP3.ROIDATA

Must set the trigger pulse width to close to the exposure time, not implemented yet

2024-10-17
4-ch Xspress3 installed and worked in 2024-2 using IOC on Zbox provided by Quantum Detectors
the ophyd device worked as is, since the data all went into the hdf
during the shutdown the IOC was moved to xf16id-ioc2, the existing code stopped working
revised based on TES example 

2025-09/26
Simplified code by making use of generate_datum() and hdf.read()

"""

xspress3_class_4ch = build_xspress3_class(
    channel_numbers=(1, 2, 3, 4),
    mcaroi_numbers=(1, 2, 3, 4),
    image_data_key="fluor",
    xspress3_parent_classes=(Xspress3Detector, Xspress3Trigger),
    extra_class_members={
        "hdf": Component(LIXhdfPlugin, "HDF1:", name="hdf", write_path_template="")
    }
)

class LiXXspress(xspress3_class_4ch):
    _trigger_signal = zebra.soft_input1
    _trigger_width = zebra.pulse1.width
    
    def __init__(self, prefix, *, f_key="fluor",
        configuration_attrs=None, read_attrs=None,
        **kwargs, ):
        self._f_key = f_key

        if configuration_attrs is None:
            configuration_attrs = [
                "external_trig",
                "total_points",
                "spectra_per_point",
                "cam",
                "rewindable",
            ]
        
        super().__init__(prefix,
            configuration_attrs=configuration_attrs,
            read_attrs=read_attrs,
            **kwargs,)

        if read_attrs is None:
            self.read_attrs = ["hdf"]  # "spectrum", "channel1", 
        self.hdf.data_dir = det_data_dir
        self.hdf.use_ioc_path = True
        self.detector_id = self.name   # this appears in the filename
        self._num_images = 1
        self._num_repeats = 1    
        self.data_key = f'{self.name}_image'
        
        if self.hdf.run_time.get()==0: # first time using the plugin
            print("warm up hdf plugin ...")
            self.hdf.warmup()
            print('done.')
            
    def stop(self, *, success=False):
        ret = super().stop()
        self.cam.acquire.put(0)
        self.hdf.stop(success=success)
        return ret

    def stage(self):
        # clean up first
        self.cam.acquire.put(0)
        self.cam.erase.put(1)
        
        makedirs(get_IOC_datapath(self.name, self.hdf.data_dir), mode=0O777)  
        # for external triggering, set pulse width based on exposure time
        """ triggerMode:
            1 = internal
            3 = TTL veto only
        """
        if self.ext_trig:
            self.cam.trigger_mode.put(3)
            self._trigger_width.put(self.cam.acquire_time.get()-0.001)  # doesn't work if same as acquire_time
        else: 
            self.cam.trigger_mode.put(1)
        self.cam.num_images.set(self._num_repeats).wait()

        status = super().stage()
        if self.ext_trig:
            self.cam.acquire.set(1).wait()

        return status

    def unstage(self):
        if self._staged == Staged.no:
            return
        print(self.name, "unstaging ...")
        super().unstage()
        print(self.name, "unstaging completed.")    
       
    def set_num_images(self, num):
        self._num_images = 1       # not aware of Xspress3 being able to do differently
        self._num_repeats = num
        self._num_captures = num   # for the hdf plugin; ??? not used anywhere???

    def set_ext_trigger(self, ext=True):
        self.ext_trig = ext

    def exp_time(self, exp_t):  ### need to implement this for Pilatus as well
        self.cam.acquire_time.set(exp_t).wait()

    def trigger(self):
        if self._staged != Staged.yes:
            raise RuntimeError("This detector is not ready to trigger."
                               "Call the stage() method before triggering.")
        print(self.name+" trigger")

        self._status = DeviceStatus(self)
        if self.ext_trig: # hardware trigger, depends on Pilatus
            self._status._finished()
        else: # internal trigger
            super().trigger()
            threading.Timer(self.cam.acquire_time.get(), self._status._finished, ()).start()
        
        self.generate_datum(self.data_key, ttime.time())
        return self._status

    def kickoff(self):
        print(f"in {self.name}.kickoff() ...")
        return NullStatus()

    def complete(self):
        print(f"in {self.name}.complete() ...")
        self.generate_datum(self.data_key, ttime.time())
        print(self.hdf._asset_docs_cache)
        return NullStatus()
    
    def collect(self):
        print(f"in {self.name} collect ...")

        datum_ids = self.hdf.read()[self.data_key]
        ret = {
            "time": time.time(),
            "data": {self.data_key: datum_ids['value']},
            "timestamps": {self.data_key: datum_ids['timestamp']},
            #"filled": {self.data_key: False},
            }
        yield ret
        
    def describe_collect(self):
        print(f"in {self.name} describe_collect ...")
        ret = {}
        ret[self.data_key] = self.make_data_key()
        ret[self.data_key]['shape'] = (self._num_repeats, *ret[self.data_key]['shape'][1:])
        for k,desc in self.describe().items():
            ret[k] = desc
        return {self.name: ret}

    def collect_asset_docs(self):
        print(f"in {self.name} collect_asset_docs")
        yield from self.hdf.collect_asset_docs()

            

try:
    xsp3 = LiXXspress("XF:16IDC-ES{Xsp:1}:", name="xsp3")
except:
    print("Xspress3 is not accessible ...")
    xsp3 = None
