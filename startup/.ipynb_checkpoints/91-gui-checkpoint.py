
def launch_lixdc():
    global username
    global proposal_id
    global run_id

    import lixdc.gui as lixdc_gui

    if username is None or proposal_id is None or run_id is None:
        login()

    lixdc_gui.run_ipython(username, proposal_id, run_id)
