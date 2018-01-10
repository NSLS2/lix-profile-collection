from ophyd import (EpicsSignal, EpicsSignalRO, Device, SingleTrigger)

class Region(Device):
    lower_limit = Cpt(EpicsSignal, "LowerLimit")
    upper_limit = Cpt(EpicsSignal, "UpperLimit")
    luminescence = Cpt(EpicsSignalRO, "Luminescence")


class USB4000(Device):
    region1 = Cpt(Region, "Region1:")
    region2 = Cpt(Region, "Region2:")
    region3 = Cpt(Region, "Region3:")
    region4 = Cpt(Region, "Region4:")
    region5 = Cpt(Region, "Region5:")

    acquire = Cpt(EpicsSignal, "Acquire", trigger_value=1)
    acquiring = Cpt(EpicsSignal, "Acquiring.RVAL")
    acquisition_mode = Cpt(EpicsSignal, "AcquisitionMode", string=True)

    time_resolution = Cpt(EpicsSignal, "IntegrationTime:Resolution", string=True)
    time_value = Cpt(EpicsSignal, "IntegrationTime:Value")

    total_luminescence = Cpt(EpicsSignalRO, "TotalLuminescence")

    spectra = Cpt(EpicsSignalRO, "Spectra")

    spectra_processed = Cpt(EpicsSignalRO, "Spectra:Processed")

    dark_cor_spectra = Cpt(EpicsSignalRO, "DarkCorrectedSpectra")
    back_cor_spectra = Cpt(EpicsSignalRO, "BackgroundSpectra")
    absorption_spectra = Cpt(EpicsSignalRO, "AbsorptionSpectra")

    dark_correction = Cpt(EpicsSignal, "ElectricalDark")

    progress_bar = Cpt(EpicsSignal, "ProgressBar")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._acquiring_status = None
        #self.stage_sigs[self.acquire] = 0 # Stop
        #self.stage_sigs[self.acquisition_mode] = 0 # Single
        #self.stage_sigs[self.time_resolution] = 1 # mSeconds

    def stage(self):
        super().stage()
        #self.acquiring.subscribe(self._acquiring_changed)
        self.progress_bar.subscribe(self._acquiring_changed)

    def unstage(self):
        super().unstage()
        #self.acquiring.clear_sub(self._acquiring_changed)
        self.progress_bar.clear_sub(self._acquiring_changed)
        self._acquiring_status = None

    def trigger(self):
        self.acquire.put(1, use_complete=True)
        self._acquiring_status = DeviceStatus(self.progress_bar)
        return self._acquiring_status

    def _acquiring_changed(self, value, old_value, **kwargs):
        if self._acquiring_status is None:
            return
        #if (old_value == 1) and (value == 0):
        #    self._acquiring_status._finished()
        if (old_value < 100.0) and (value == 100.0):
            self._acquiring_status._finished()


usb4000 = USB4000("SA0000-03:", name="usb4000")
