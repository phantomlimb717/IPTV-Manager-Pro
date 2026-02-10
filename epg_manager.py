from PySide6.QtCore import QThread, Signal
import logging
from stalker_integration import StalkerPortal

logger = logging.getLogger(__name__)

class EpgManager(QThread):
    epg_ready = Signal(str, list)

    def __init__(self, portal_url, mac_address):
        super().__init__()
        self.portal_url = portal_url
        self.mac_address = mac_address
        self.queue = []
        self._is_running = True
        self.portal = None

    def request_epg(self, channel_id):
        if channel_id not in self.queue:
            self.queue.append(channel_id)

    def stop(self):
        self._is_running = False
        if not self.isFinished():
            self.requestInterruption()
            self.wait(2000) # Wait up to 2 seconds then force terminate if needed to prevent hangs
            if self.isRunning():
                 self.terminate()
                 self.wait()

    def run(self):
        # Initialize one portal session for the EPG thread
        try:
            self.portal = StalkerPortal(self.portal_url, self.mac_address)
            if not self.portal.handshake():
                 logger.error("EPG Manager: Handshake failed.")
                 return
            self.portal.get_profile() # Ensure valid session
        except Exception as e:
            logger.error(f"EPG Manager: Initialization failed: {e}")
            return

        while self._is_running and not self.isInterruptionRequested():
            if self.queue:
                ch_id = self.queue.pop(0)
                try:
                    # Fetch EPG for next 2 hours (7200s)
                    data = self.portal.get_epg(ch_id, period=7200)
                    if data:
                        self.epg_ready.emit(str(ch_id), data)
                except Exception as e:
                    logger.error(f"EPG fetch error for {ch_id}: {e}")

                self.msleep(200)
            else:
                self.msleep(500)
