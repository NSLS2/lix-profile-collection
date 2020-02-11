import faulthandler
faulthandler.enable()
import logging,sys

import nslsii

# override base
# hopefully should be PR to nslsii
def import_star(module, ns):
    public = lambda name: not name.startswith('_')
    ns.update({name: getattr(module, name)
                        for name in dir(module) if public(name)})


def configure_base(user_ns, broker_name, *,
                   bec=True, epics_context=True, magics=True, mpl=True,
                   ophyd_logging=True, pbar=True):
    """
    Perform base setup and instantiation of important objects.

    This factory function instantiates the following and adds them to the
    namespace:

    * ``RE`` -- a RunEngine
    * ``db`` -- a Broker (from "databroker"), subscribe to ``RE``
    * ``bec`` -- a BestEffortCallback, subscribed to ``RE``
    * ``peaks`` -- an alias for ``bec.peaks``
    * ``sd`` -- a SupplementalData preprocessor, added to ``RE.preprocessors``
    * ``pbar_maanger`` -- a ProgressBarManager, set as the ``RE.waiting_hook``

    And it performs some low-level configuration:

    * creates a context in ophyd's control layer (``ophyd.setup_ophyd()``)
    * turns out interactive plotting (``matplotlib.pyplot.ion()``)
    * bridges the RunEngine and Qt event loops
      (``bluesky.utils.install_kicker()``)
    * logs ERROR-level log message from ophyd to the standard out

    Parameters
    ----------
    user_ns: dict
        a namespace --- for example, ``get_ipython().user_ns``
    broker_name : Union[str, Broker]
        Name of databroker configuration or a Broker instance.
    bec : boolean, optional
        True by default. Set False to skip BestEffortCallback.
    epics_context : boolean, optional
        True by default. Set False to skip ``setup_ophyd()``.
    magics : boolean, optional
        True by default. Set False to skip registration of custom IPython
        magics.
    mpl : boolean, optional
        True by default. Set False to skip matplotlib ``ion()`` at event-loop
        bridging.
    ophyd_logging : boolean, optional
        True by default. Set False to skip ERROR-level log configuration for
        ophyd.
    pbar : boolean, optional
        True by default. Set false to skip ProgressBarManager.

    Returns
    -------
    names : list
        list of names added to the namespace

    Examples
    --------
    Configure IPython for CHX.

    >>>> configure_base(get_ipython().user_ns, 'chx');
    """
    ns = {}  # We will update user_ns with this at the end.

    # Test if we are in Jupyter or IPython:
    in_jupyter = user_ns['get_ipython']().has_trait('kernel')

    # Set up a RunEngine and use metadata backed by a sqlite file.
    from bluesky import RunEngine
    from bluesky.utils import get_history
    # if RunEngine already defined grab it
    # useful when users make their own custom RunEngine
    if 'RE' in user_ns:
        RE = user_ns['RE']
    else:
        RE = RunEngine(get_history())
        ns['RE'] = RE

    # Set up SupplementalData.
    # (This is a no-op until devices are added to it,
    # so there is no need to provide a 'skip_sd' switch.)
    from bluesky import SupplementalData
    sd = SupplementalData()
    RE.preprocessors.append(sd)
    ns['sd'] = sd

    if isinstance(broker_name, str):
        # Set up a Broker.
        from databroker import Broker
        db = Broker.named(broker_name)
        ns['db'] = db
    else:
        db = broker_name

    RE.subscribe(db.insert)

    if pbar and not in_jupyter:
        # Add a progress bar.
        from bluesky.utils import ProgressBarManager
        pbar_manager = ProgressBarManager()
        RE.waiting_hook = pbar_manager
        ns['pbar_manager'] = pbar_manager

    if magics:
        # Register bluesky IPython magics.
        from bluesky.magics import BlueskyMagics
        get_ipython().register_magics(BlueskyMagics)

    if bec:
        # Set up the BestEffortCallback.
        from bluesky.callbacks.best_effort import BestEffortCallback
        _bec = BestEffortCallback()
        bec = _bec
        RE.subscribe(_bec)
        if in_jupyter:
            _bec.disable_plots()
        ns['bec'] = _bec
        ns['peaks'] = _bec.peaks  # just as alias for less typing

    if mpl:
        # Import matplotlib and put it in interactive mode.
        import matplotlib.pyplot as plt
        ns['plt'] = plt
        plt.ion()

        # Commented to allow more intelligent setting of kickers (for Jupyter and IPython):
        ## Make plots update live while scans run.
        # from bluesky.utils import install_kicker
        # install_kicker()

        # Make plots update live while scans run.
        if in_jupyter:
            from bluesky.utils import install_nb_kicker
            install_nb_kicker()
        else:
            from bluesky.utils import install_qt_kicker
            install_qt_kicker()

    if not ophyd_logging:
        # Turn on error-level logging, particularly useful for knowing when
        # pyepics callbacks fail.
        import logging
        import ophyd.ophydobj
        ch = logging.StreamHandler()
        ch.setLevel(logging.ERROR)
        ophyd.ophydobj.logger.addHandler(ch)

    # convenience imports
    # some of the * imports are for 'back-compatibility' of a sort -- we have
    # taught BL staff to expect LiveTable and LivePlot etc. to be in their
    # namespace
    import numpy as np
    ns['np'] = np

    import bluesky.callbacks
    ns['bc'] = bluesky.callbacks
    import_star(bluesky.callbacks, ns)

    import bluesky.plans
    ns['bp'] = bluesky.plans
    import_star(bluesky.plans, ns)

    import bluesky.plan_stubs
    ns['bps'] = bluesky.plan_stubs
    import_star(bluesky.plan_stubs, ns)
    # special-case the commonly-used mv / mvr and its aliases mov / movr4
    ns['mv'] = bluesky.plan_stubs.mv
    ns['mvr'] = bluesky.plan_stubs.mvr
    ns['mov'] = bluesky.plan_stubs.mov
    ns['movr'] = bluesky.plan_stubs.movr

    import bluesky.preprocessors
    ns['bpp'] = bluesky.preprocessors

    import bluesky.callbacks.broker
    import_star(bluesky.callbacks.broker, ns)
    import bluesky.simulators
    import_star(bluesky.simulators, ns)

    user_ns.update(ns)
    return list(ns)


from databroker import Broker
# TODO : move to /etc/databroker/lix.yml
# and use :
# nslsii.configure_base(get_ipython().user_ns, 'lix')
db_config = {
    'description' : 'LIX production mongo',
    'metadatastore' : {
        'module': 'databroker.headersource.mongo',
        'class' : 'MDS',
        'config' :{
            'host': 'xf16idc-ca',
            'port': 27017,
            'database': 'metadatastore_production_v1',
            'timezone': 'US/Eastern'
        },
    },
    'assets': {
        'module' : 'databroker.assets.mongo',
        'class' : 'Registry',
        'config':{
            'host': 'xf16idc-ca',
            'port': 27017,
            'database': 'filestore',
        },
    },
}

db = Broker.from_config(db_config)
bec = None


#import bluesky
#from ophyd import *
#from ophyd.commands import *

def reload_macros(file='~/.ipython/profile_collection/startup/99-macros.py'):
    ipy = get_ipython()
    ipy.magic('run -i '+file)


def is_ipython():
    ip = True
    if 'ipykernel' in sys.modules:
        ip = False # Notebook
    elif 'IPython' in sys.modules:
        ip = True # Shell
    return ip


# def setup_LIX(user_ns, mode):
#     ns = {}
#     ns.update(lix_base())
#     if mode == 'scanning':
#         user_ns['motor'] = EpicsMotor(...)
# 
#     elif mode == 'solution':
#         ...
# 
#     user_ns.update(ns)
#     return list(ns)
# 
# 
# def new_login():
#     ...
# 
#     setup_LIX(ip.user_ns, ...)
