print(f"Loading {__file__}...")

import asyncio
from traitlets import HasTraits, TraitType, Unicode, List, Float, Bool, link
from bluesky.utils import get_history
from functools import partial
from bluesky.run_engine import RunEngine
from bluesky.callbacks import LiveTable
from bluesky.callbacks.olog import logbook_cb_factory

# Subscribe metadatastore to documents.
# If this is removed, data is not saved to metadatastore.

#from bluesky.global_state import gs

global DETS 

# moved to 00-base.py during 2020-2 deployment
#class CustomRunEngine(RunEngine):
#    def __call__(self, *args, **kwargs):
#        global username
#        global proposal_id
#        global run_id
#
#        if username is None or proposal_id is None or run_id is None:
#            login()
#
#        return super().__call__(*args, **kwargs)

#RE = CustomRunEngine()

#configure_base(get_ipython().user_ns, db, bec=True, pbar=False)
# end of code moved to 00-base.py

#abort = RE.abort
#resume = RE.resume
#stop = RE.stop

RE.md['group'] = 'lix'
RE.md['beamline_id'] = 'LIX'

DETS = []
