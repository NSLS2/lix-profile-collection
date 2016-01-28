import asyncio
from functools import partial
from bluesky.standard_config import *
from bluesky.plans import *
from bluesky.callbacks import *
from bluesky.broker_callbacks import *
from bluesky.callbacks.olog import logbook_cb_factory
from bluesky.hardware_checklist import *
from bluesky.qt_kicker import install_qt_kicker
from pyOlog import SimpleOlogClient



# The following line allows bluesky and pyqt4 GUIs to play nicely together:
install_qt_kicker()

RE = gs.RE
abort = RE.abort
resume = RE.resume
stop = RE.stop

RE.md['group'] = ''
RE.md['beamline_id'] = 'LIX'
# RE.ignore_callback_exceptions = False

loop = asyncio.get_event_loop()
loop.set_debug(False)
# RE.verbose = True

# sr_shutter_status = EpicsSignal('SR-EPS{PLC:1}Sts:MstrSh-Sts', rw=False,
#                                 name='sr_shutter_status')
# sr_beam_current = EpicsSignal('SR:C03-BI{DCCT:1}I:Real-I', rw=False,
#                               name='sr_beam_current')

checklist = partial(basic_checklist,
                    ca_url='http://xf16idc-ca.cs.nsls2.local:17668/',
                    #disk_storage=[('/', 10e9), ('/data', 10e9), ('/xspress3_data', 10e9)],
                    # pv_names=['XF:23ID1-ES{Dif-Ax:SY}Pos-SP'],
                    # pv_conditions=[('XF:23ID-PPS{Sh:FE}Pos-Sts', 'front-end shutter is open', assert_pv_equal, 0),
                    # 		   ('XF:23IDA-PPS:1{PSh}Pos-Sts', 'upstream shutter is open', assert_pv_equal, 0),
                    #                ('XF:23ID1-PPS{PSh}Pos-Sts', 'downstream shutter is open', assert_pv_equal, 0)],
		    )

# Set up the logbook. This configured bluesky's summaries of
# data acquisition (scan type, ID, etc.). It does NOT affect the
# convenience functions in ophyd (log_pos, etc.) or the IPython
# magics (%logit, %grabit). Those are configured in ~/.pyOlog.conf
# or wherever the pyOlog configuration file is stored.

LOGBOOKS = ['Commissioning']  # list of logbook names to publish to
simple_olog_client = SimpleOlogClient()
generic_logbook_func = simple_olog_client.log
configured_logbook_func = partial(generic_logbook_func, logbooks=LOGBOOKS)

cb = logbook_cb_factory(configured_logbook_func)
RE.subscribe('start', cb)

