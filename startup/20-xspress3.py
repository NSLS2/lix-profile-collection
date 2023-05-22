print(f"Loading {__file__}...")

from nslsii.detectors.xspress3 import XspressTrigger,Xspress3Detector,Xspress3Channel,Xspress3FileStore

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

"""
IMPORTANT:
Since the device is from the detector pool, there is no guarantee that all parameters are loaded 
correctly when the IOC starts. This particular one has caused persistent problem.

lyang@xf16id-ws3:xf16id1$ caput XF:16IDC-ES{Xsp:1}:ARR1:NDArrayPort XSP3
Old : XF:16IDC-ES{Xsp:1}:ARR1:NDArrayPort XSP3.ROI1
New : XF:16IDC-ES{Xsp:1}:ARR1:NDArrayPort XSP3

"""



class LiXXspress(XspressTrigger, Xspress3Detector):
    """ adapted from SRX
        use internal trigger for now
    """
    roi_data = Cpt(PluginBase, "ROIDATA:")
    erase = Cpt(EpicsSignal, "ERASE")
    array_counter = Cpt(EpicsSignal, "ArrayCounter_RBV")
    num_frames = Cpt(EpicsSignal, "NumImages")
    _triggerMode = Cpt(EpicsSignal, "TriggerMode")
    ext_trig = False

    channel1 = Cpt(Xspress3Channel, "C1_", channel_num=1, read_attrs=["rois"])
    spectrum = Cpt(ImagePlugin, "ARR1:", read_attrs=["array_data"])
    acq_time = Cpt(EpicsSignal, "AcquireTime")
    _trigger_signal = EpicsSignal('XF:16IDC-ES{Zeb:1}:SOFT_IN:B0')
    _trigger_width = EpicsSignal("XF:16IDC-ES{Zeb:1}:PULSE2_WID")
   
    def __init__(self, prefix, *, f_key="fluor",
        configuration_attrs=None, read_attrs=None,
        **kwargs, ):
        self._f_key = f_key
        if configuration_attrs is None:
            configuration_attrs = [
                "external_trig",
                "total_points",
                "spectra_per_point",
                "settings",
                "rewindable",
            ]
        if read_attrs is None:
            read_attrs = ["channel1", "spectrum"] #"hdf5"]
        super().__init__(prefix,
            configuration_attrs=configuration_attrs,
            read_attrs=read_attrs,
            **kwargs,)
        self._exp_time = self.acq_time.get()
        self._triggerMode.put(1)   # internal

    def stop(self, *, success=False):
        ret = super().stop()
        self.settings.acquire.put(0)
        #self.hdf5.stop(success=success)
        return ret

    def stage(self):
        # for external triggering, set pulse width based on exposure time
        if self.ext_trig:
            self._triggerMode.put(3)
            self._trigger_width.put(self.acq_time.get())
        else: 
            self._triggerMode.put(1)

        status = super().stage()
        if self.ext_trig:
            self._acquisition_signal.set(1).wait()

        return status

    def unstage(self):
        if self._staged == Staged.no:
            return
        print(self.name, "unstaging ...")
        super().unstage()
        print(self.name, "unstaging completed.")    
       
    def set_ext_trigger(self, ext=True):
        """ triggerMode:
            1 = internal
            3 = TTL veto only
        """
        self.ext_trig = ext

    def exp_time(self, exp_t):  ### need to implement this for Pilatus as well
        self.acq_time.put(exp_t, wait=True)

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
            threading.Timer(self.acq_time.get(), self._status._finished, ()).start()
        
        return self._status

try:
    xsp3 = LiXXspress("XF:16IDC-ES{Xsp:1}:", name="xsp3")
    xsp3.channel1.rois.read_attrs = ["roi{:02}".format(j) for j in [1, 2, 3, 4]]
except:
    print("Xspress3 is not accessible ...")

