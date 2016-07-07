import asyncio
from traitlets import HasTraits, TraitType, Unicode, List, Float, Bool, link
from bluesky.utils import get_history
from functools import partial
from bluesky.run_engine import RunEngine
from bluesky.plans import InnerProductAbsScanPlan, InnerProductDeltaScanPlan, Count, count
from bluesky.spec_api import ct
from bluesky.callbacks import *
from bluesky.callbacks.olog import logbook_cb_factory

# Subscribe metadatastore to documents.
# If this is removed, data is not saved to metadatastore.
import metadatastore.commands
from bluesky.global_state import gs

class CustomRunEngine(RunEngine):
    def __call__(self, *args, **kwargs):
        global username
        global proposal_id
        global run_id

        if username is None or proposal_id is None or run_id is None:
            login()
        
        return super().__call__(*args, **kwargs)

RE = CustomRunEngine()
gs.RE = RE
gs.RE.subscribe_lossless('all', metadatastore.commands.insert)

# Import matplotlib and put it in interactive mode.
import matplotlib.pyplot as plt
plt.ion()

# Make plots update live while scans run.
from bluesky.utils import install_qt_kicker
install_qt_kicker()

RE = gs.RE
abort = RE.abort
resume = RE.resume
stop = RE.stop

RE.md['group'] = 'lix'
RE.md['beamline_id'] = 'LIX'
# RE.verbose = True

# sr_shutter_status = EpicsSignal('SR-EPS{PLC:1}Sts:MstrSh-Sts', rw=False,
#                                 name='sr_shutter_status')
# sr_beam_current = EpicsSignal('SR:C03-BI{DCCT:1}I:Real-I', rw=False,
#                               name='sr_beam_current')

