from collections import ChainMap
from ophyd import DeviceStatus
from bluesky.plans import (monitor_during_decorator, kickoff, complete,
                           collect, run_decorator, stage_decorator,
                           trigger_and_read, subs_decorator, monitor, unmonitor)
from bluesky.callbacks import LivePlot


class LoudLivePlot(LivePlot):
    def event(self, doc):
        if 'usb4000_region1_luminscence' in doc['data']:
            print(doc['seq_num'])
        super().event(doc)


def hplc_scan(detectors, monitors, *, md=None):
    if md is None:
        md = {}
    md = ChainMap(md,
                  {'plan_name': 'hplc_scan'})

    @fast_shutter_decorator() 
    #@subs_decorator(LiveTable([usb4000.region1.luminescence.name]))
    #@subs_decorator(LoudLivePlot(usb4000.region1.luminescence.name))
    @stage_decorator([hplc] + detectors)
    #@monitor_during_decorator(monitors)
    @run_decorator(md=md)
    def inner():
        print('Beamline Ready... waiting for HPLC Injected Signal')
        yield from kickoff(hplc, wait=True)
        print('Acquiring data...')
        for mo in monitors:
            yield from monitor(mo)
        status = yield from complete(hplc, wait=False)
        while True:
            yield from trigger_and_read(detectors)  # one 'primary' event per loop
            if status.done:
                break
        for mo in monitors:
            yield from unmonitor(mo)
        print('Collecting the data...')
        yield from collect(hplc)

    return (yield from inner())

def collect_hplc(sample_name,exp):#, CV=24, flowrate=0.5)
    change_sample(sample_name)
    #time = CV/flowrate
    #no_of_cts = time * 60/exp
    set_pil_num_images(1)
    pilatus_ct_time(exp)
    updata_metadata()
    RE(hplc_scan(detectors=[pil1M, pilW1, pilW2, em1, em2], monitors=[]))

