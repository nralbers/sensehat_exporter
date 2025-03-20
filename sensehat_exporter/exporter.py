import asyncio
import logging
import math
import os
import subprocess
from collections import namedtuple
from enum import Enum, StrEnum, auto

from fastapi import FastAPI
from prometheus_client import REGISTRY, make_asgi_app
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from sense_hat import ACTION_RELEASED, InputEvent, SenseHat

logger = logging.getLogger("uvicorn.error")

# Create single instance of sensehat object
sense = SenseHat()

# SETTINGS
TEMPERATURE_CALIBRATION = float(os.environ.get("TEMPERATURE_CALIBRATION", "0.0"))
PRESSURE_CALIBRATION = float(os.environ.get("PRESSURE_CALIBRATION", "0.0"))
HUMIDITY_CALIBRATION = float(os.environ.get("HUMIDITY_CALIBRATION", "0.0"))


# Git stats for current project
def get_git_revision_hash() -> str:
    return subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode('ascii').strip()

def get_git_branch() -> str:
    return subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).decode('ascii').strip()

def get_tagged_version() -> str:
    return subprocess.check_output(['git', 'describe', '--tags', '--abbrev=0']).decode('ascii').strip()

# state machine for display
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
        collector_info = GaugeMetricFamily(
            "sense_hat_version_info",
            "SenseHat Exporter version info",
            labels=["version","branch", "commit"]
        )
        collector_info.add_metric([get_tagged_version(),get_git_branch(), get_git_revision_hash()],1)
        yield collector_info
        
        temperature_calibration = GaugeMetricFamily(
            "sense_hat_temperature_calibration",
            "Temperature calibration offset",
            value=TEMPERATURE_CALIBRATION,
            unit="celsius"
        )
        yield temperature_calibration
        
        temperature = GaugeMetricFamily(
            "sense_hat_temperature",
            "Sense hat temperature in °C",
            labels=["sensor", "calibrated"],
            unit="celsius",
        )
        temperature.add_metric(
            ["humidity", "false"], value=self.sense.get_temperature_from_humidity()
        )
        temperature.add_metric(
            ["pressure", "false"], value=self.sense.get_temperature_from_pressure()
        )
        temperature.add_metric(
            ["humidity", "true"], value=self.sense.get_temperature_from_humidity() + TEMPERATURE_CALIBRATION
        )
        temperature.add_metric(
            ["pressure", "true"], value=self.sense.get_temperature_from_pressure() + TEMPERATURE_CALIBRATION
        )
        yield temperature
        
        pressure_calibration = GaugeMetricFamily(
            "sense_hat_pressure_calibration",
            "Pressure calibration offset",
            value=PRESSURE_CALIBRATION,
            unit="mbar"
        )
        yield pressure_calibration
        
        pressure = GaugeMetricFamily(
            "sense_hat_pressure",
            "Sense Hat pressure in mb",
            labels=["calibrated"],
            unit="mbar",
        )
        pressure.add_metric(["false"], value=self.sense.get_pressure())
        pressure.add_metric(["true"], value=self.sense.get_pressure() + PRESSURE_CALIBRATION)
        yield pressure
        
        humidity_calibration = GaugeMetricFamily(
            "sense_hat_humidity_calibration",
            "Relative Humidity calibration offset",
            value=HUMIDITY_CALIBRATION,
            unit="percent"
        )
        yield humidity_calibration
        
        humidity = GaugeMetricFamily(
            "sense_hat_relative_humidity",
            "Sense Hat Relative Humidity in %",
            labels=["calibrated"],
            unit="percent",
        )
        humidity.add_metric(["false"], value=self.sense.get_humidity())
        humidity.add_metric(["true"], value=self.sense.get_humidity() + HUMIDITY_CALIBRATION)
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
