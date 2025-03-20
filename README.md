# Sense HAT exporter for raspberry pi

## Installation
Clone this repo to a folder on your raspberry pi

### Requirements
You will need to install the following python libraries using apt

```bash
sudo apt install python3-prometheus-client
sudo apt install python3-fastapi
sudo apt install gunicorn3
```

## Usage
In the root folder of the repository, run
```bash
gunicorn sensehat_exporter.exporter:app
```


## Caveats
The sense_hat library is single-process, single-threaded. This means that if you are running this exporter on a device with the sense_hat, you cannot run any other code using
the sense_hat library or the sensor readout will return either 0 or random undefined values.
