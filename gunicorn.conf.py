import logging

from sense_hat import SenseHat

logger = logging.getLogger("uvicorn.error")

bind = "0.0.0.0:11011"
worker_class = "uvicorn.workers.UvicornWorker"


def on_exit(server):
    logger.info("[Stopping display loop]")
    sense = SenseHat()
    sense.show_message("bye!")
    sense.low_light = False
    sense.clear()
    logger.info("[Stopping display loop] Done")
