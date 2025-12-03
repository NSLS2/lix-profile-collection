print(f"Loading {__file__}...")

import bluesky.plans as bp
import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp

USE_FAST_SHUTTER = True

def fast_shutter_wrapper(plan):
    #update_metadata()

    if USE_FAST_SHUTTER:
        plan = bpp.pchain(bps.abs_set(fast_shutter.output, FastShutter.OPEN_SHUTTER, settle_time=FastShutter.SETTLE_TIME), plan)
        plan = bpp.finalize_wrapper(plan, 
                                    bps.abs_set(fast_shutter.output,
                                                FastShutter.CLOSE_SHUTTER,
                                                settle_time=FastShutter.SETTLE_TIME))

    return (yield from plan)

fast_shutter_decorator = bpp.make_decorator(fast_shutter_wrapper)


