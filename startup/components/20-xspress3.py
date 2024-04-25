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


2023-10-20
atempting to use in fly scans and save data in hdf
hdf plugin array port: originally XSP3.ROIDATA

Must set the trigger pulse width to close to the exposure time, not implemented yet

"""

class LiXXspress(XspressTrigger, Xspress3Detector):
    """ adapted from SRX
    """
    roi_data = Cpt(PluginBase, "ROIDATA:")
    erase = Cpt(EpicsSignal, "ERASE")
    array_counter = Cpt(EpicsSignal, "ArrayCounter_RBV")
    num_frames = Cpt(EpicsSignal, "NumImages")
    _triggerMode = Cpt(EpicsSignal, "TriggerMode")
    ext_trig = True

    channel1 = Cpt(Xspress3Channel, "C1_", channel_num=1, read_attrs=["rois"])
    spectrum = Cpt(ImagePlugin, "ARR1:", read_attrs=["array_data"])
    acq_time = Cpt(EpicsSignal, "AcquireTime")
    _trigger_signal = EpicsSignal('XF:16IDC-ES{Zeb:1}:SOFT_IN:B0')
    _trigger_width = EpicsSignal("XF:16IDC-ES{Zeb:1}:PULSE2_WID")
    _num_captures = 1

    hdf = Cpt(LIXhdfPlugin, suffix="HDF5:",   # note the number, this is from the detector pool IOC
              write_path_template="", root='/')
    #codec1 = Cpt(CodecPlugin, "Codec1:")
    
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
            read_attrs = ["hdf"]  # "spectrum", "channel1", 
        super().__init__(prefix,
            configuration_attrs=configuration_attrs,
            read_attrs=read_attrs,
            **kwargs,)
        self.cam = self.settings   # to be compatible with AD plugins
        self._exp_time = self.acq_time.get()
        self._triggerMode.put(1)   # internal
        self.hdf.data_dir = xspress3_data_dir
        self.hdf.use_ioc_path = True
        self.detector_id = self.name   # this appears in the filename
        self._num_images = 1
        self._flying = False
        
        if self.hdf.run_time.get()==0: # first time using the plugin
            self.hdf.warmup()

    def stop(self, *, success=False):
        ret = super().stop()
        self.settings.acquire.put(0)
        self.hdf.stop(success=success)
        return ret

    def stage(self):
        # detector pool Xspress3 IOC cannot create directories 
        makedirs(get_IOC_datapath(self.name, self.hdf.data_dir), mode=0O777)  
        # for external triggering, set pulse width based on exposure time
        if self.ext_trig:
            self._triggerMode.put(3)
            self._trigger_width.put(self.acq_time.get())
        else: 
            self._triggerMode.put(1)
        self.num_frames.set(self._num_images).wait()

        status = super().stage()
        if self.ext_trig:
            self._acquisition_signal.set(1).wait()
        self.datum={}

        return status

    def unstage(self):
        if self._staged == Staged.no:
            return
        self._flying = False
        print(self.name, "unstaging ...")
        super().unstage()
        print(self.name, "unstaging completed.")    
       
    def set_num_images(self, num):
        self._num_images = num
        self._num_captures = num   # for the hdf plugin

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
    
    # complete/collect/collect_asset_docs revised from SRX code
    # skipping channels and frames
    """  this needs to be revised following 20-pilatus; move the code from collect_asset_docs() here
    def complete(self, *args, **kwargs):
        print(f'In {self.name}.complete()...')
        self._asset_docs_cache = []
        for resource in self.hdf._asset_docs_cache:
            self._asset_docs_cache.append(('resource', resource[1]))

        #self._datum_ids = []
        #num_frames = self.cam.array_counter.get()
        #for frame_num in range(num_frames):
        #    for channel in self.iterate_channels():
        #        datum_id = '{}/{}'.format(self.hdf._resource_uid, 0)
        #        datum = {'resource': self.hdf._resource_uid,
        #                 'datum_kwargs': {'frame': frame_num, 'channel': channel.channel_number},
        #                 'datum_id': datum_id}
        #        self._asset_docs_cache.append(('datum', datum))
        #        self._datum_ids.append(datum_id)

        datum_id = '{}/{}'.format(self.hdf._resource_uid, 0)
        datum = {'resource': self.hdf._resource_uid,
                 'datum_id': datum_id,
                 'datum_kwargs': {'point_number': 0}}
        self._asset_docs_cache.append(('datum', datum))
        self._datum_ids.append(datum_id)

        print("asset_docs_cache with datums:", self._asset_docs_cache)
        return NullStatus()
    """

    def kickoff(self):
        return NullStatus()

    def complete(self):
        return NullStatus()
    
    def collect(self):
        """
        collected_frames = self.hdf.num_captured.get()
        for frame_num in range(collected_frames):
            # print(f'  frame_num in "collect": {frame_num + 1} / {collected_frames}')

            datum_id = self._datum_ids[frame_num]
            ts = ttime.time()

            data = {self.name: datum_id}
            ts = float(ts)
            yield {'data': data,
                   'timestamps': {key: ts for key in data},
                   'time': ts,  # TODO: use the proper timestamps from the ID/mono start and stop times
                   'filled': {key: False for key in data}}
        """        
        print(f"in {self.name} collect ...")
        data = {}
        ts = {}
        k = f'{self.name}_image'
        data[k],ts[k] = self.datum[k]
                    
        ret = {'time': time.time(),
               'data': data,
               'timestamps': ts,
              }
        
        yield ret

    def describe_collect(self):
        print(f"in {self.name} describe_collect ...")
        ret = {}
        ret[f'{self.name}_image'] = self.make_data_key()
        ret[f'{self.name}_image']['shape'] = (self._num_images, *ret[f'{self.name}_image']['shape'][1:])
        for k,desc in self.describe().items():
            ret[k] = desc
        return {self.name: ret}

    def collect_asset_docs(self):
        print(f"in {self.name} collect_asset_docs")
        if self._flying:   # to-do: this should be implemented under complete() 
            asset_docs_cache = []
            for resource in self.hdf._asset_docs_cache:
                asset_docs_cache.append(('resource', resource[1]))

            k = f'{self.name}_image'
            datum_id = '{}/{}'.format(self.hdf._resource_uid, 0)
            self.datum[k] = [datum_id, ttime.time()]
            datum = {'resource': self.hdf._resource_uid,
                     'datum_id': datum_id,
                     'datum_kwargs': {'point_number': 0}}
            asset_docs_cache.append(('datum', datum))

            print("+++", asset_docs_cache)
            print("---", self.datum)
            yield from tuple(asset_docs_cache)
        else:
            yield from self.hdf.collect_asset_docs()
            

try:
    xsp3 = LiXXspress("XF:16IDC-ES{Xsp:1}:", name="xsp3")
    xsp3.channel1.rois.read_attrs = ["roi{:02}".format(j) for j in [1, 2, 3, 4]]
    caput('XF:16IDC-ES{Xsp:1}:ARR1:NDArrayPort', "XSP3")
except:
    print("Xspress3 is not accessible ...")
    xsp3 = None

