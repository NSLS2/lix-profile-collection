import faulthandler
faulthandler.enable()
import logging
import sys

from bluesky.run_engine import RunEngine
import nslsii


class CustomRunEngine(RunEngine):
    def __call__(self, *args, **kwargs):
        global username
        global proposal_id
        global run_id

        if username is None or proposal_id is None or run_id is None:
            login()

        return super().__call__(*args, **kwargs)

RE = CustomRunEngine()

nslsii.configure_base(get_ipython().user_ns, 'lix', bec=True, pbar=False)

# this is temporary until ophyd v1.5.3
logging.getLogger("ophyd").setLevel("WARNING")

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


# this is for backward compatibility with bluesky 1.5.x
# eventually this will be removed
from pathlib import Path

import appdirs


try:
    from bluesky.utils import PersistentDict
except ImportError:
    import msgpack
    import msgpack_numpy
    import zict

    class PersistentDict(zict.Func):
        def __init__(self, directory):
            self._directory = directory
            self._file = zict.File(directory)
            super().__init__(self._dump, self._load, self._file)

        @property
        def directory(self):
            return self._directory

        def __repr__(self):
            return f"<{self.__class__.__name__} {dict(self)!r}>"

        @staticmethod
        def _dump(obj):
            "Encode as msgpack using numpy-aware encoder."
            # See https://github.com/msgpack/msgpack-python#string-and-binary-type
            # for more on use_bin_type.
            return msgpack.packb(
                obj,
                default=msgpack_numpy.encode,
                use_bin_type=True)

        @staticmethod
        def _load(file):
            return msgpack.unpackb(
                file,
                object_hook=msgpack_numpy.decode,
                raw=False)

runengine_metadata_dir = appdirs.user_data_dir(appname="bluesky") / Path("runengine-metadata")

# PersistentDict will create the directory if it does not exist
RE.md = PersistentDict(runengine_metadata_dir)

