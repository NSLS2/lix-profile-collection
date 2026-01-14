print(f"Loading {__file__}...")

from ophyd import Component as Cpt
from ophyd.areadetector.cam import AreaDetectorCam
from ophyd.areadetector.detectors import DetectorBase
from nslsii.ad33 import CamV33Mixin,SingleTriggerV33
from ophyd import EpicsSignal, EpicsSignalRO

""" based on xspress3 code
    KineticCam from FXI
"""

class KinetixCam(CamV33Mixin, AreaDetectorCam):
    readout_port_idx = Cpt(EpicsSignal, "ReadoutPortIdx")
    readout_port_names = ('Sensitivity', 'Speed', 'Dynamic Range', 'Sub-Electron')
    speed_idx = Cpt(EpicsSignal, "SpeedIdx")
    gain_idx = Cpt(EpicsSignal, "GainIdx")
    apply_readout_mode = Cpt(EpicsSignal, "ApplyReadoutMode")
    readout_mode_state = Cpt(EpicsSignalRO, "ReadoutModeValid_RBV")
    data_type = Cpt(EpicsSignalRO, "DataType_RBV")
    aquire_status = Cpt(EpicsSignalRO, "StatusMessage_RBV")
    
    def __init__(self, *args, **kwargs):
        AreaDetectorCam.__init__(self, *args, **kwargs)
        self.stage_sigs["wait_for_plugins"] = "Yes"

class LiXKinetix(SingleTriggerV33, DetectorBase):
    cam = Cpt(KinetixCam, "cam1:")
    hdf = Cpt(LIXhdfPlugin, suffix="HDF1:", write_path_template="", root='/')
    trans = Cpt(TransformPlugin, 'Trans1:')
    codec1 = Cpt(CodecPlugin, "Codec1:")
    _trigger_signal = zebra.soft_input1
    
    def __init__(self, prefix, *,
        configuration_attrs=None, read_attrs=None,
        **kwargs, ):

        super().__init__(prefix,
            configuration_attrs=configuration_attrs,
            read_attrs=read_attrs,
            **kwargs,)
        """
        if configuration_attrs is None:
            configuration_attrs = [
                #"external_trig",
                #"total_points",
                "hdf",
                "cam",
                #"rewindable",
            ]
        """
        if read_attrs is None:
            self.read_attrs = ["hdf"]  

        self.ext_trig = True
        self.hdf.data_dir = det_data_dir
        self.hdf.use_ioc_path = True
        self.detector_id = self.name   # this appears in the filename
        self._num_images = 1
        self._num_repeats = 1
        self._num_captures = 1
        self.data_key = f'{self.name}_image'
        
        if self.hdf.run_time.get()==0: # first time using the plugin
            self.hdf.warmup()
            
    def stop(self, *, success=False):
        ret = super().stop()
        self.cam.acquire.put(0)
        self.hdf.stop(success=success)
        return ret

    def stage(self):
        # clean up first
        self.cam.acquire.put(0)
        
        makedirs(get_IOC_datapath(self.name, self.hdf.data_dir), mode=0O777)  
        # for external triggering, set pulse width based on exposure time
        """ triggerMode:
            0 = internal
            1 = rising edge
        """
        #self.stage_sigs.update([('image_mode', "Multiple"), 
        #                        ('trigger_mode', "Rising Edge"), ])
        status = super().stage()

        #""" # ext_trig only???
        if self.ext_trig:
            self.cam.trigger_mode.set(1).wait()
        else: 
            self.cam.trigger_mode.set(0).wait()
        self.cam.image_mode.set(1).wait()   # multiple
        #"""
        self.cam.num_images.set(self._num_images*self._num_repeats).wait()

        if self.ext_trig:
            self.cam.acquire.set(1).wait()

        return status

    def unstage(self):
        if self._staged == Staged.no:
            return
        print(self.name, "unstaging ...")
        super().unstage()
        print(self.name, "unstaging completed.")    
       
    def set_num_images(self, n_triggers, img_per_trig=1):
        self._num_images = img_per_trig
        self._num_repeats = n_triggers
        self._num_captures = n_triggers*img_per_trig     # for the hdf plugin

    def set_ext_trigger(self, ext=True):
        self.ext_trig = ext
    
    def exp_time(self, exp_t, time_between_frames=0.001):  
        self.cam.acquire_time.set(exp_t).wait()
        self.cam.acquire_period.set(exp_t+time_between_frames).wait()

    def describe(self):
        res = super().describe()
        res[self.data_key] = self.make_data_key()
        return res
    
    def trigger(self):
        if self._staged != Staged.yes:
            raise RuntimeError("This detector is not ready to trigger."
                               "Call the stage() method before triggering.")
        print(self.name+" trigger")

        self._status = DeviceStatus(self)
        if self.ext_trig: # hardware trigger, depends on ext_trig
            self._status._finished()
        else: # internal trigger
            super().trigger()
            #threading.Timer(self.cam.acquire_time.get(), self._status._finished, ()).start()
        
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
        ret[self.data_key]['shape'] = (self._num_images, *ret[self.data_key]['shape'][1:])
        for k,desc in self.describe().items():
            ret[k] = desc
        return {self.name: ret}

    def collect_asset_docs(self):
        print(f"in {self.name} collect_asset_docs")
        yield from self.hdf.collect_asset_docs()

try:
    ktx22 = LiXKinetix("XF:16ID-ES{Kinetix-Det:1}", name="ktx22")
except:
    print("Kinetix22 is not accessible ...")
    ktx22 = None
