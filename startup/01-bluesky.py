import asyncio
from traitlets import HasTraits, TraitType, Unicode, List, Float, Bool, link
from bluesky.utils import get_history
from functools import partial
from bluesky.run_engine import RunEngine
from bluesky.callbacks import *
from bluesky.callbacks.olog import logbook_cb_factory

# Subscribe metadatastore to documents.
# If this is removed, data is not saved to metadatastore.
from metadatastore.mds import MDS
from databroker import Broker
from databroker.core import register_builtin_handlers
from filestore.fs import FileStore

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

mds = MDS({'host': 'xf16idc-ca',
           'database': 'metadatastore_production_v1',
           'port': 27017,
           'timezone': 'US/Eastern'}, auth=False)

db = Broker(mds, FileStore({'host': 'xf16idc-ca',
                            'database': 'filestore',
                            'port': 27017}))

register_builtin_handlers(db.fs)
RE.subscribe('all', mds.insert)

if is_ipython():
    # FIXME: Remove this once we migrate to PYTHON 3.5
    from IPython import get_ipython
    from IPython.core.pylabtools import backend2gui
    from matplotlib import get_backend
    ip = get_ipython()
    ipython_gui_name = backend2gui.get(get_backend())
    if ipython_gui_name:
        ip.enable_gui(ipython_gui_name)

    # Import matplotlib and put it in interactive mode.
    import matplotlib.pyplot as plt
    plt.ion()

    # Make plots update live while scans run.
    from bluesky.utils import install_qt_kicker
    install_qt_kicker()
    print("Installing Qt Kicker...")
else:
    # Import matplotlib and put it in interactive mode.
    import matplotlib.pyplot as plt
    plt.ion()

    from bluesky.utils import install_nb_kicker
    install_nb_kicker()

RE = gs.RE
abort = RE.abort
resume = RE.resume
stop = RE.stop

RE.md['group'] = 'lix'
RE.md['beamline_id'] = 'LIX'

