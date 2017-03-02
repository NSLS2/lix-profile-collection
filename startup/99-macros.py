from time import sleep 
from epics import caget,caput

def mov_all(motor, pos, wait=True, relative=False):
    if relative:
        pos += motor.position
    motor.move(pos, wait=wait)

def ct_time(exp):
    pil1M.cam.acquire_time.put(exp)
    pilW1.cam.acquire_time.put(exp)
    pilW2.cam.acquire_time.put(exp)