import bluesky.plans as bsp

gs.USE_FAST_SHUTTER = True


def fast_shutter_wrapper(plan):
    if gs.USE_FAST_SHUTTER:
        plan = bsp.pchain(bsp.abs_set(fast_shutter.output, FastShutter.OPEN_SHUTTER, settle_time=FastShutter.SETTLE_TIME), plan)
        plan = bsp.finalize_wrapper(plan, bsp.abs_set(fast_shutter.output, FastShutter.CLOSE_SHUTTER, settle_time=FastShutter.SETTLE_TIME))
    return (yield from plan)

fast_shutter_decorator = bsp.make_decorator(fast_shutter_wrapper)

ct = fast_shutter_decorator(ct)

