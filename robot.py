import __future__

from datetime import datetime
import json
import logging
import os
import paho.mqtt.client as mqtt
import sys
import requests
import threading
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

class Robot(object):

    def __init__(self, conf):

        self.conf = conf
        self.tick_interval_sec = self.conf['tick_interval_sec']
        self.init()

        self.stop_event = threading.Event()
        self.loop = threading.Thread(target=self.loop_func)

    def init(self):
        self.init_credential()
        self.init_mqtt_client()

        self.init_role()
        self.init_local_state()
        self.init_task_state()

    def init_credential(self):
        if self.conf['account_id'] and self.conf['robot_id'] and self.conf['secret']:
            self.cellular_access = False
            self.credential = {
                "account_id": self.conf['account_id'],
                "robot_id": self.conf['robot_id'],
                "secret": self.conf['secret']
            }

            self.headers = {
                'content-type':'application/json',
                'x-ciraas-robotid':self.credential['robot_id'],
                'x-ciraas-robot-secret':self.credential['secret']
            }

        else:
            r = requests.get('http://beam.soracom.io/robot')
            credential = r.json()
            self.cellular_access = True
            self.credential = {
                "account_id": credential['accountId'],
                "robot_id": credential['robotId']
            }

    def init_mqtt_client(self):

        self.ciraas_mqtt_client = mqtt.Client(client_id=self.credential['robot_id'])

        if self.cellular_access:
            self.mqtt_api = 'beam.soracom.io'
            self.mqtt_port = 1883
        else:
            self.mqtt_api = 'mqtt.ciraas.io'
            self.mqtt_port = 8883

            self.ciraas_mqtt_client.tls_set(ca_certs=os.environ['CA_CERT'])
            self.ciraas_mqtt_client.username_pw_set(
                self.conf['robot_id'],
                password=self.conf['secret']
            )

        self.ciraas_mqtt_client.on_connect = self.ciraas_on_connect
        self.ciraas_mqtt_client.on_message = self.ciraas_on_message

        self.base_uplink_mqtt_topic = 'uplink/{}/robot/{}'.format(
            self.credential['account_id'],
            self.credential['robot_id'])

    def start_mqtt_client(self):
        logger.info('connecting to ' + self.mqtt_api)
        self.ciraas_mqtt_client.connect(self.mqtt_api, self.mqtt_port, 60)
        self.ciraas_mqtt_client.loop_start()

    def init_role(self):
        logger.wan('You should implement init_role in your child class, otherwise we set this emtpy')
        self.role  = '';

    def init_local_state(self):
        logger.warn('You should implement init_local_state in your child class, otherwise we set this emtpy')
        self.local_state = {}

    def init_task_state(self):
        logger.wanr('You should implement init_task_state in your child class, otherwise we set this emtpy')
        self.task_state = {}

    def publish_state(self, key, value):
        data = json.dumps({"state": value})
        self.ciraas_mqtt_client.publish(self.base_uplink_mqtt_topic + '/state/' + key, payload=data)

    def publish_ros_message(self,topic,data):
        self.ciraas_mqtt_client.publish(self.base_uplink_mqtt_topic + '/ros_message' + topic, payload=data) 

    def post(self,path, data=None):
        if self.cellular_access:
            r = requests.post(
                'http://beam.soracom.io' + path,
                data=data
            )
        else:
            r = requests.post(
                'https://api.ciraas.io' + path,
                data=data,
                headers=self.headers
            )
        return r

    def put(self,path, data=None):
        if self.cellular_access:
            r = requests.put(
                'http://beam.soracom.io' + path,
                data=data
            )
        else:
            r = requests.put(
                'https://api.ciraas.io' + path,
                data=data,
                headers=self.headers
            )
        return r

    def post_state(self, key, value):
        data = json.dumps({"state": value})
        self.post('/robot/state/' + key, data)

    def post_image(self, path, image):

        if self.cellular_access:
            r = requests.put(
                'http://beam.soracom.io/object/' + path,
                data=data
            )
        else:
            r = requests.put(
                'https://api.ciraas.io/object/' + path,
                data=data,
                headers=self.headers
            )
        print(r.status_code)


    def ack_download_task(self, download_id):
        r = self.put('/message/download/' + download_id)
        print(r.status_code)
        print(r.text)

    def loop_func(self):

        self.start_mqtt_client()

        while not self.stop_event.is_set():
            self.tick()
            time.sleep(self.tick_interval_sec)

    def tick(self):
        raise Exception('Override tick. We call this method every tick of main loop.')
            
    def ciraas_on_connect(self,client,userdata,flags,rc):
        logger.info("Conntected to CIRaaS: " +  self.credential['robot_id'])
        topic = '{}/robot/{}/#'.format(
            self.credential['account_id'],
            self.credential['robot_id'])

        self.ciraas_mqtt_client.subscribe(topic)
        logger.info('Suscribed to: ' + topic)
        self.init_app()

    def init_app(self):
        logger.warn('Override this, otherwise we do nothing.')
        pass

    def ciraas_on_message(self,client,userdata,msg):
        self.on_msg(json.loads(msg.payload))

    def on_msg(self,msg):
        message_type = msg['messageType']
        logger.info('Message recieved. MessageType: ' + message_type)
        if message_type == 'download_task':
            self.on_download_task(msg)
        if message_type == 'partial_state_update':
            self.on_partial_state_update(msg)
        if message_type == 'whole_state_update':
            self.on_whole_state_update(msg)

    def on_download_task(self, msg):
        logger.warn('Override this, otherwise we do nothing.')
        logger.wanr(msg)

    def on_partial_state_update(self, msg):
        logger.warn('Override this, otherwise we do nothing.')
        logger.wanr(msg)

    def on_whole_state_update(self, msg):
        logger.warn('Override this, otherwise we do nothing.')
        logger.wanr(msg)

    def stop(self):
        self.stop_event.set()

    def run(self):
        self.loop.start()
