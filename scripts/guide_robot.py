import __future__

import importlib
from datetime import datetime
import json
import logging
import sys
import time
import random
import requests
import rospy

from rosbridge_library.internal import message_conversion
from zipfile import ZipFile

import actionlib
from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

sys.path.append('/home/ubuntu/catkin_ws/src/guide_robot')
from robot import Robot

class GuideRobot(Robot):

    def __init__(self,conf):
        super(GuideRobot, self).__init__(conf)

        self.rosq = {}
        rospy.init_node(conf["robot_id"].replace("-",""))

        for topic in conf["subscribe"]:
          topic_name = topic[0]
          [module,msg_type]  = topic[1].split("/")
          module = importlib.import_module(module + ".msg")
          rospy.Subscriber(topic_name, getattr(module,msg_type), self.ros_on_message, callback_args=[conf["robot_id"],topic_name])

    def call_for_task(self):
      task = {"task_state":{"call_for_task":True}}
      self.set_task(task)
      self.report_task_state()

    # Override
    def init_app(self):
      self.call_for_task()

    # Override
    def init_role(self):
        self.role = 'guide_robot'

    # Override
    def init_local_state(self):
        self.local_state = {
            "battery": 100,
            "status": "operational",
            "not_on_duty":0
        }

    # Override
    def init_task_state(self):
        self.task_state = {}

    # Override
    def tick(self):
        self.consume_battery()
        self.report_local_state()
        self.update_task_state()
        self.report_ros_message()
        self.check_duty()

    def serialize(self, data):
      return json.dumps(message_conversion.extract_values(data))

    def check_duty(self):
      self.local_state['not_on_duty'] += 1
      if self.local_state['not_on_duty'] > 30:
        self.call_for_task()

    def clear_no_duty_term(self):
      self.local_state['not_on_duty'] = 0

    def report_ros_message(self):
      for topic in self.rosq.keys():
        serialized = self.serialize(self.rosq[topic])
        #print(topic,serialized)
        self.publish_ros_message(topic, serialized)

    def ros_on_message(self, data,args):
      [robot_id,topic_name] = args
      self.rosq[topic_name] = data

    def report_local_state(self):
        print('reporting local state', self.local_state)
        self.publish_state('local_state', self.local_state)

    def report_task_state(self):
        print('reporting task state', self.task_state)
        self.publish_state('task_state', self.task_state)

    def update_task_state(self):
      task = self.task_state
      if 'task_id' in task.keys() and not 'status' in task.keys():
        logger.info('starting task')
        self.start_task()

    def start_task(self):

      if self.local_state['battery'] < 20:
        self.dock_and_charge()

      self.clear_no_duty_term()

      self.mark_task_started()
      self.move()
      self.consume_battery(5)
      self.mark_task_completed()

    def dock_and_charge(self):
      self.local_state['status'] = 'charging'
      self.report_local_state()
      self.charge_battery()
      self.local_state['status'] = 'operational'
      self.report_local_state()

    def mark_task_started(self):
      self.task_state['started_at'] = datetime.now().isoformat()
      self.task_state['status'] = 'started'
      self.task_state['robot_id'] = self.credential['robot_id']
      logger.info(self.task_state['task_id'] + " started by " + self.credential['robot_id'])
      self.report_task_state()

    def mark_task_completed(self):
      self.task_state['completed_at'] = datetime.now().isoformat()
      self.task_state['status'] = 'completed'
      logger.info(json.dumps(self.task_state) + " completed by " + self.credential['robot_id'])
      self.report_task_state()

    def consume_battery(self,num=None):
        if self.local_state['battery'] > 0:
            if not num:
              num = random.randint(0,2)
            self.local_state['battery'] -= num

    def charge_battery(self):
        time.sleep(60)
        logger.info(self.credential['robot_id'], 'battery chaerged!')
        self.local_state['battery'] = 100

    # Override
    def on_partial_state_update(self, msg):
        if 'task_state' in msg['payload'].keys():
            logger.info('Received a new task message from cloud!')
            print(msg['payload'])
            self.set_task(msg['payload'])

    def set_task(self, task):
        logger.info('Updating task: ' + json.dumps(task['task_state']))
        self.task_state = task['task_state']

    def move(self):
      client = actionlib.SimpleActionClient('move_base',MoveBaseAction)
      client.wait_for_server()
      goal = MoveBaseGoal()
      goal.target_pose.header.frame_id = "map"
      goal.target_pose.header.stamp = rospy.Time.now()
      goal.target_pose.pose.position.x = self.task_state['waypoint']['x']
      goal.target_pose.pose.position.y = self.task_state['waypoint']['y']
      goal.target_pose.pose.orientation.w = 1.0
      client.send_goal(goal)
      wait = client.wait_for_result(rospy.Duration.from_sec(60.0))

      if not wait:
          rospy.logerr("Action server not available!")
          rospy.signal_shutdown("Action server not available!")
          client.cancel_goal()
          self.call_for_task()
          return True
      else:
          return client.get_result()

    # Override
    def on_download_task(self, msg):
        task = msg['payload']
        logger.info('received a new download task' + task['downloadId'])
        r = requests.get(task['signedUrl'])
        
        with open('/tmp/' + task['objectName'], 'wb') as f:
            f.write(r.content)

        self.ack_download_task(task['downloadId'])
        logger.info('completed download task: ' + task['downloadId'])
