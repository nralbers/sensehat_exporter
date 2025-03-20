import asyncio
import logging
import math
from collections import namedtuple
from enum import Enum, StrEnum, auto

from fastapi import FastAPI
from prometheus_client import REGISTRY, make_asgi_app
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from sense_hat import ACTION_RELEASED, InputEvent, SenseHat

logger = logging.getLogger("uvicorn.error")


class DisplayState(StrEnum):
    TEMP = auto()
    PRESSURE = auto()
    HUMIDITY = auto()
    DEFAULT = auto()


state: DisplayState = DisplayState.DEFAULT


class Colours(Enum):
    R = 0
    G = 1
    B = 2


WHITE = [255, 255, 255]
W = WHITE
RED = [255, 0, 0]
R = RED
GREEN = [0, 255, 0]
G = GREEN
BLUE = [0, 0, 255]
B = BLUE
CYAN = [0, 255, 255]
C = CYAN
YELLOW = [255, 255, 0]
Y = YELLOW
X = [0, 0, 0]

SCROLL_SPEED = 0.075
PROCESS_LOOP_DELAY_SEC = 0.5


Readings = namedtuple("Readings", ["temp", "humidity", "pressure"])

# Create single instance of sensehat object
sense = SenseHat()


def pushed_middle(event: InputEvent):
    if event.action != ACTION_RELEASED:
        global state
        logger.info("[BUTTONS] middle button pressed")
        state = DisplayState.DEFAULT


def pushed_up(event: InputEvent):
    if event.action != ACTION_RELEASED:
        global state
        logger.info("[BUTTONS] up button pressed")
        state = DisplayState.TEMP


def pushed_left(event: InputEvent):
    if event.action != ACTION_RELEASED:
        global state
        logger.info("[BUTTONS] left button pressed")
        state = DisplayState.HUMIDITY


def pushed_right(event: InputEvent):
    if event.action != ACTION_RELEASED:
        global state
        logger.info("[BUTTONS] right button pressed")
        state = DisplayState.PRESSURE


def get_env_readings() -> Readings:
    temp = sense.temperature
    pressure = sense.pressure
    humidity = sense.humidity

    return Readings(temp=temp, pressure=pressure, humidity=humidity)


def get_gradient_function(start_rgb, end_rgb, min_val: float, max_val: float):
    def gradient_function(value):
        ratio = (value - min_val) / (max_val - min_val)
        colour = list()
        for col in Colours:
            col_val = (end_rgb[col.value] - start_rgb[col.value]) * ratio + start_rgb[
                col.value
            ]
            colour.append(math.floor(col_val))
        return colour

    return gradient_function


def get_temperature_colour(value):
    low_gradient = get_gradient_function(WHITE, BLUE, -20, 0)
    med_gradient = get_gradient_function(BLUE, GREEN, 0, 20)
    high_gradient = get_gradient_function(GREEN, RED, 20, 40)
    if value < -20:
        return WHITE
    elif value >= -20 and value < 0:
        return low_gradient(value)
    elif value >= 0 and value < 20:
        return med_gradient(value)
    elif value >= 20 and value < 40:
        return high_gradient(value)
    else:
        return RED


def get_humidity_colour(value):
    low_gradient = get_gradient_function(WHITE, BLUE, 0, 30)
    med_gradient = get_gradient_function(BLUE, GREEN, 30, 60)
    high_gradient = get_gradient_function(GREEN, RED, 60, 100)
    if value < 0:
        return WHITE
    elif value >= 0 and value < 30:
        return low_gradient(value)
    elif value >= 30 and value < 60:
        return med_gradient(value)
    elif value >= 60 and value < 100:
        return high_gradient(value)
    else:
        return RED


def display_readings(readings: Readings):
    global state
    if state == DisplayState.TEMP:
        temp = readings.temp
        colour = get_temperature_colour(temp)
        sense.show_message(
            f"{temp:.1f}C", scroll_speed=SCROLL_SPEED, text_colour=colour
        )
        state = DisplayState.DEFAULT
    elif state == DisplayState.HUMIDITY:
        humidity = readings.humidity
        colour = get_humidity_colour(humidity)
        sense.show_message(
            f"{humidity:.0f}%", scroll_speed=SCROLL_SPEED, text_colour=colour
        )
        state = DisplayState.DEFAULT
    elif state == DisplayState.PRESSURE:
        pressure = readings.pressure
        colour = YELLOW
        sense.show_message(
            f"{pressure:.0f}mb", scroll_speed=SCROLL_SPEED, text_colour=colour
        )
        state = DisplayState.DEFAULT
    elif state == DisplayState.DEFAULT:
        sense.set_pixel(7, 7, 100, 0, 0)


class CustomCollector(Collector):
    def __init__(self, sense: SenseHat):
        self.sense = sense

    def collect(self):
        temperature = GaugeMetricFamily(
            "sense_hat_temperature",
            "Sense hat temperature in °C",
            labels=["sensor"],
            unit="celsius",
        )
        temperature.add_metric(
            ["humidity"], value=self.sense.get_temperature_from_humidity()
        )
        temperature.add_metric(
            ["pressure"], value=self.sense.get_temperature_from_pressure()
        )
        yield temperature
        pressure = GaugeMetricFamily(
            "sense_hat_pressure",
            "Sense Hat pressure in mb",
            value=self.sense.get_pressure(),
            unit="mbar",
        )
        yield pressure
        humidity = GaugeMetricFamily(
            "sense_hat_relative_humidity",
            "Sense Hat Relative Humidity in %",
            value=self.sense.get_humidity(),
            unit="percent",
        )
        yield humidity
        orientation_degrees = GaugeMetricFamily(
            "sense_hat_orientation",
            "Sense Hat orientation in degrees",
            labels=["axis"],
            unit="degrees",
        )
        orientation_radians = GaugeMetricFamily(
            "sense_hat_orientation",
            "Sense Hat orientation in Radians",
            labels=["axis"],
            unit="radians",
        )
        for axis in ["pitch", "roll", "yaw"]:
            orientation_degrees.add_metric(
                [axis], value=self.sense.get_orientation_degrees()[axis]
            )
            yield orientation_degrees
            orientation_radians.add_metric(
                [axis], value=self.sense.get_orientation_radians()[axis]
            )
            yield orientation_radians


async def displayloop():
    sense.low_light = True
    RUNNING = True
    while RUNNING:
        readings = get_env_readings()
        display_readings(readings)
        await asyncio.sleep(PROCESS_LOOP_DELAY_SEC)


sense.stick.direction_middle = pushed_middle
sense.stick.direction_up = pushed_up
sense.stick.direction_left = pushed_left
sense.stick.direction_right = pushed_right

# Create app
app = FastAPI(debug=False)
REGISTRY.register(CustomCollector(sense))


@app.on_event("startup")
async def startup_event():
    logger.info("[Starting display loop]")
    asyncio.create_task(displayloop())


# Add prometheus asgi middleware to route /metrics requests

metrics_app = make_asgi_app()

app.mount("/metrics", metrics_app)
