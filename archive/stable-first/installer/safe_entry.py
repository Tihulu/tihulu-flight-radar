"""Stable First passive Qt entry. Keeps original source untouched.

Only reads existing receiver data. It intentionally refuses all mutating
receiver operations in preserved v0.3.1, whose global service lifecycle is
unsafe for two concurrent application versions. Hardware parity remains HOLD.
"""
import os

if os.environ.get("TIHULU_STABLE_FIRST_PASSIVE") != "1":
    raise SystemExit("Stable First refuses an unisolated launch")

from tihulu_flight_radar import control


def _deny(*_args, **_kwargs):
    raise control.DataError(
        "Stable First is read-only: Start/Stop/Restart and systemd/USB ownership "
        "are disabled until an independent hardware safety review."
    )


def _passive_close(self, release_local_service=False):
    # Do not call legacy close(): it could stop a borrowed readsb.service.
    if self.process is not None:
        # A direct process should be impossible because start() is blocked.
        raise control.DataError("Unexpected direct decoder ownership; refusing service release")
    return None


control.service_action = _deny
control.ReceiverController.start = _deny
control.ReceiverController.stop = _deny
control.ReceiverController.restart = _deny
control.ReceiverController.close = _passive_close

# The classic dashboard imports service_action by value; load it only AFTER
# patching the original controller. The GUI and map source are not modified.
from tihulu_flight_radar.native import main

if __name__ == "__main__":
    raise SystemExit(main())
