"""Bluesky plans for configuring and firing the BioFluidix injector.

"""

from bluesky import plan_stubs as bps


def configure_bfx_group(
    *,
    ch3_drops,
    ch4_drops,
    ch3_velocity=75,
    ch4_velocity=75,
    pipe_id="500-S",
    frequency=10,
):
    """Configure channels 3 and 4 for one simultaneous group fire."""
    if ch3_drops < 0 or ch4_drops < 0:
        raise ValueError("Drop counts cannot be negative")
    if ch3_drops == 0 and ch4_drops == 0:
        raise ValueError("At least one channel must have a nonzero drop count")

    yield from bps.mv(
        bfx.mode, "Group",
        bfx.advance_after_fire, "No",
        bfx.frequency, frequency,
        bfx.ch1.enable, "Disabled",
        bfx.ch2.enable, "Disabled",
        bfx.ch3.enable, "Enabled" if ch3_drops > 0 else "Disabled",
        bfx.ch4.enable, "Enabled" if ch4_drops > 0 else "Disabled",
        bfx.ch3.drops, ch3_drops,
        bfx.ch4.drops, ch4_drops,
        bfx.ch3.stroke_velocity, ch3_velocity,
        bfx.ch4.stroke_velocity, ch4_velocity,
        bfx.ch3.pipe_id, pipe_id,
        bfx.ch4.pipe_id, pipe_id,
    )


def fire_bfx_once():
    """Fire the configured channels once and wait for success or failure."""
    yield from bps.trigger(bfx, group="bfx_fire")
    yield from bps.wait(group="bfx_fire")


def inject_then(
    plan,
    *,
    ch3_drops,
    ch4_drops,
    ch3_velocity=75,
    ch4_velocity=75,
    pipe_id="500-S",
    frequency=10,
):
    """Configure and fire once, then execute any supplied Bluesky plan."""
    yield from configure_bfx_group(
        ch3_drops=ch3_drops,
        ch4_drops=ch4_drops,
        ch3_velocity=ch3_velocity,
        ch4_velocity=ch4_velocity,
        pipe_id=pipe_id,
        frequency=frequency,
    )
    yield from fire_bfx_once()
    return (yield from plan)
