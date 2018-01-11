import asyncio
from traitlets import HasTraits, TraitType, Unicode, List, Float, Bool, link
from bluesky.utils import get_history
from functools import partial
from bluesky.run_engine import RunEngine
from bluesky.callbacks import *
from bluesky.callbacks.olog import logbook_cb_factory
from bluesky.spec_api import setup_livetable

# Subscribe metadatastore to documents.
# If this is removed, data is not saved to metadatastore.
from metadatastore.mds import MDS
from databroker import Broker
from databroker.core import register_builtin_handlers

#from bluesky.global_state import gs


class CustomRunEngine(RunEngine):
    def __call__(self, *args, **kwargs):
        global username
        global proposal_id
        global run_id

        if username is None or proposal_id is None or run_id is None:
            login()

        return super().__call__(*args, **kwargs)

RE = CustomRunEngine()
#gs.RE = RE

register_builtin_handlers(db.reg)

#RE = gs.RE
abort = RE.abort
resume = RE.resume
stop = RE.stop

RE.md['group'] = 'lix'
RE.md['beamline_id'] = 'LIX'

# define list of DET's used globally
class gs:
    DETS = []

# this should get rid of the the live plots but keep the live table
#gs.SUB_FACTORIES['dscan'] = [setup_livetable]
#gs.SUB_FACTORIES['ascan'] = [setup_livetable]
#gs.SUB_FACTORIES['d2scan'] = [setup_livetable]
#gs.SUB_FACTORIES['a2scan'] = [setup_livetable]
#gs.SUB_FACTORIES['ct'] = [setup_livetable]
#gs.SUB_FACTORIES['mesh'] = [setup_livetable]
