#!/usr/bin/env python

import __future__

import json
from guide_robot import GuideRobot
import signal
import sys

if __name__ == '__main__':
    
    conf_path = sys.argv[1]
    with open(conf_path) as f:
        confs = json.load(f)['robots']

    robots = []
    for conf in confs:
        robots.append(GuideRobot(conf))

    print(robots[0].local_state)

    def start_handler():
        for robot in robots:
                robot.run()
    
    def stop_handler(signum, frame):
        print(signum)
        for robot in robots:
                robot.stop()

    start_handler()
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    signal.pause()
