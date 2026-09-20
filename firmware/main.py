"""Entry point: bring the eye up, then serve it over the network.

Nothing here reads a pin. The upstream firmware polled a joystick, two
switches and a trim potentiometer, and this build has none of them.

Without secrets.py, or when the access point does not answer, the eye holds the
neutral pose. It moves when something asks it to and at no other time, so a
missing network leaves it still rather than animating to an empty room.
"""

import asyncio

import eyemech

eye = eyemech.Eye()
eye.neutral()


async def main():
    try:
        import wifi
        address = wifi.connect()
    except (ImportError, OSError) as exc:
        # neutral() already ran, and nothing else writes to the chip, so the
        # servos hold that pose. There is no loop to keep here.
        print("no network (%s); holding neutral" % exc)
        return

    import server
    await server.serve(eye)
    asyncio.create_task(wifi.supervise())
    print("eye ready on http://%s/" % address)
    while True:
        await asyncio.sleep(3600)


try:
    asyncio.run(main())
except KeyboardInterrupt:
    # Ctrl-C leaves six servos holding position otherwise, each drawing its
    # full current against whatever the linkage rests on.
    eye.release()
