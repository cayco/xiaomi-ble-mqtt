#!/usr/bin/python3

from mitemp.mitemp_bt.mitemp_bt_poller import MiTempBtPoller
from mitemp.mitemp_bt.mitemp_bt_poller import MI_TEMPERATURE, MI_HUMIDITY, MI_BATTERY
from btlewrap.bluepy import BluepyBackend
from bluepy.btle import BTLEException
import paho.mqtt.publish as publish
import traceback
import configparser
import os
import json
import datetime
import argparse
import re
import sys
import logging
import time

from mikettle.mikettle import MiKettle
from mikettle.mikettle import (
  MI_ACTION,
  MI_MODE,
  MI_SET_TEMPERATURE,
  MI_CURRENT_TEMPERATURE,
  MI_KW_TYPE,
  MI_KW_TIME
)

workdir = os.path.dirname(os.path.realpath(__file__))
config = configparser.ConfigParser()
config.read("{0}/devices.ini".format(workdir))

devices = config.sections()

# Averages
averages = configparser.ConfigParser()
averages.read("{0}/averages.ini".format(workdir))

messages = []
def valid_mikettle_mac(mac, pat=re.compile(r"[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}")):
    """Check for valid mac adresses."""
    if not pat.match(mac.upper()):
        raise argparse.ArgumentTypeError('The MAC address "{}" seems to be in the wrong format'.format(mac))
    return mac


def valid_product_id(product_id):
    try:
        product_id = int(product_id)
    except Exception:
        raise argparse.ArgumentTypeError('The Product Id "{}" seems to be in the wrong format'.format(product_id))
    return product_id

def kettle_connect(args):
    """Connect to Mi Kettle."""

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)

    kettle = MiKettle(args.get("device_mac"), int(args.get("product_id")))
    print("Authenticating")
    print("Getting data from mi Kettle")

    try:
      print("Current temperature: {}".format(kettle.parameter_value(MI_CURRENT_TEMPERATURE)))
    except Exception as error:
      print("Read failed")
      print(error)
    return kettle

def read_devices():
        for device in devices:
            mac = config[device].get("device_mac")
            if config[device].get("device_type") != "mikettle":
                poller = MiTempBtPoller(mac, BluepyBackend, ble_timeout=config[device].getint("timeout", 10))
                try:
                    temperature = poller.parameter_value(MI_TEMPERATURE)
                    humidity = poller.parameter_value(MI_HUMIDITY)
                    battery = poller.parameter_value(MI_BATTERY)
                
                    data = json.dumps({
                        "temperature": temperature,
                        "humidity": humidity,
                        "battery": battery
                    })
                
                    print(datetime.datetime.now(), device, " : ", data)
                    messages.append({'topic': config[device].get("topic"), 'payload': data, 'retain': config[device].getboolean("retain", False)})
                    availability = 'online'
                except BTLEException as e:
                    availability = 'offline'
                    print(datetime.datetime.now(), "Error connecting to device {0}: {1}".format(device, str(e)))
                except Exception as e:
                    availability = 'offline'
                    print(datetime.datetime.now(), "Error polling device {0}. Device might be unreachable or offline.".format(device))
                    # print(traceback.print_exc())
                finally:
                    messages.append({'topic': config[device].get("availability_topic"), 'payload': availability, 'retain': config[device].getboolean("retain", False)})
            else:
                kettle = kettle_connect(config[device])
                data = json.dumps({
                    "current_temperature": kettle.parameter_value(MI_CURRENT_TEMPERATURE),
                    "set_temperature": kettle.parameter_value(MI_SET_TEMPERATURE),
                    "action": kettle.parameter_value(MI_ACTION),
                    "mode": kettle.parameter_value(MI_MODE),
                    "warm_type": kettle.parameter_value(MI_KW_TYPE)
                })
                messages.append({'topic': config[device].get("topic"), 'payload': data, 'retain': config[device].getboolean("retain", False)})
            sendMQTT()
def sendMQTT(): 
        # Init MQTT
        mqtt_config = configparser.ConfigParser()
        mqtt_config.read("{0}/mqtt.ini".format(workdir))
        mqtt_broker_cfg = mqtt_config["broker"]
        
        try:
            auth = None
            mqtt_username = mqtt_broker_cfg.get("username")
            mqtt_password = mqtt_broker_cfg.get("password")
        
            if mqtt_username:
                auth = {"username": mqtt_username, "password": mqtt_password}
        
            publish.multiple(messages, hostname=mqtt_broker_cfg.get("host"), port=mqtt_broker_cfg.getint("port"), client_id=mqtt_broker_cfg.get("client"), auth=auth)
        except Exception as ex:
            print(datetime.datetime.now(), "Error publishing to MQTT: {0}".format(str(ex)))
        
        with open("{0}/averages.ini".format(workdir), "w") as averages_file:
            averages.write(averages_file)
        
def main():
    read_devices()

if __name__ == '__main__':
    main()
