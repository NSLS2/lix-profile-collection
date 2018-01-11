from pyOlog import SimpleOlogClient


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

nslsii.configure_olog(get_ipython().user_ns, callback=cb)
