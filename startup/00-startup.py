import logging

from ophyd.session import get_session_manager

session_mgr = get_session_manager()
session_mgr._logger.setLevel(logging.INFO)

# To help with debugging scanning-related problems, uncomment the following:
# session_mgr._logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stderr)
fmt = logging.Formatter("%(asctime)-15s [%(name)5s:%(levelname)s] %(message)s")
handler.setFormatter(fmt)

from ophyd.commands import *
#from dataportal import (DataBroker as db,
#                        StepScan as ss,
#                        DataBroker, StepScan,
#                        DataMuxer)

