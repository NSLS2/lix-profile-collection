import logging

import ophyd
ophyd.utils.startup.setup()

import bluesky
from ophyd import *
from ophyd.commands import *

from databroker import DataBroker as db, get_table, get_images, get_events
from datamuxer import DataMuxer

def reload_macros(file='~/.ipython/profile_collection/startup/99-macros.py'):
    ipy = get_ipython()
    ipy.magic('run -i '+file)

