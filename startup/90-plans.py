from collections import ChainMap
from ophyd import DeviceStatus
from bluesky.preprocessors import (monitor_during_decorator, run_decorator,
                                   stage_decorator, subs_decorator)
from bluesky.plan_stubs import (complete, kickoff, collect, monitor, unmonitor,
                                trigger_and_read)
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
    sol.select_flow_cell('middle')
    #time = CV/flowrate
    #no_of_cts = time * 60/exp
    set_pil_num_images(1)
    pilatus_ct_time(exp)
    updata_metadata()
    RE(hplc_scan(detectors=[pil1M, pilW1, pilW2, em1, em2], monitors=[]))


## Plotting instructions
## Method 1 : Using Best Effort Callback
## enable live table
#bec.enable_table()
## enable plots
#bec.enable_plots()


## add hints for ex:
#ss2.y.hints = {'fields': ['ss2_y', 'ss2_y_user_setpoint']}

## use em1.describe() to find the fields you can use, then choose them with:
#em1.hints = {'fields': ['em1_current1_mean_value', 'em1_current2_mean_value']}

#RE(relative_scan(DETS, ss2.y, -1,1, 10))


## Method 1 : Directly using LiveTable
#bec.disable_table()
#bec.disable_plots()
## run RE on LiveTable with all the field names
#RE(relative_scan(DETS, ss2.y, -1,1, 10), LiveTable(['ss2_y', 'ss2_y_user_setpoint']))
