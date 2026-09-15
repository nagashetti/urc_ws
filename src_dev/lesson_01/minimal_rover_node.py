#!/usr/bin/env python3
"""Lesson 1: the smallest ROS 2 node that does something useful.

This is the first real code you'd write for the URC console project, right
after locking in the message contract (../msg/*.msg). It publishes a fixed
GPS fix on a timer — nothing else yet. Every later feature (movement,
commands, the GUI reacting to telemetry) is built on this exact shape: a
Node subclass with a publisher and a timer.

Compare this to the real thing at
src/urc_rover_sim/urc_rover_sim/rover_sim_node.py — same skeleton, just with
four more publishers, five subscribers, and a drive controller layered on.
"""

import rclpy

# In ROS 2, rclpy is the Python client library that lets you write ROS nodes in Python, and Node is the base class for all ROS 2 nodes. This line is the standard starting point for creating a node that can publish, subscribe, and interact with the ROS graph.
# When you write a class like class MyRoverNode(Node):, you are extending the ROS 2 base node class. That gives your class access to important functionality such as creating publishers, subscribers, timers, parameters, and service clients. In practice, this is the “core object” that turns a regular Python program into a ROS node.
# This import matters because ROS 2 nodes are not just plain Python scripts; they need to integrate with the ROS runtime. By inheriting from Node, your code can participate in the executor loop, communicate with topics, and be managed by the ROS 2 system in the same way as any other node. Without this import, you would not have the standard ROS 2 node lifecycle and APIs available.
from rclpy.node import Node

# This line imports the NavSatFix message type from the sensor_msgs package in ROS 2. In ROS, messages are reusable data structures that define the format of data sent over topics. sensor_msgs is the standard package for sensor-related messages, and NavSatFix is the message used to represent GPS fix data such as latitude, longitude, altitude, and status information.
# In the rover node, this import is important because the node is going to publish GPS data on a topic like /rover/gps. The node will create a publisher using self.create_publisher(NavSatFix, '/rover/gps', 10), which means the publisher is explicitly typed to send NavSatFix messages. That type safety matters because ROS subscribers and publishers must agree on the message structure, otherwise they cannot communicate correctly.
# In other words, this single import is the “contract” that tells Python and ROS: “the data we are publishing on this topic is GPS fix information.” Without it, the node would not know how to construct or send a valid ROS GPS message.
from sensor_msgs.msg import NavSatFix


class MinimalRoverNode(Node):
    """Publishes a fixed GPS position at a fixed rate. That's the whole job."""

    def __init__(self):
        # Every rclpy node needs a name — this is how it shows up in
        # `ros2 node list` and in rqt_graph.
        super().__init__('minimal_rover')

        # A ROS parameter: settable at launch time or live with
        # `ros2 param set`, without touching code or rebuilding. This one
        # habit is what makes the real sim's fault injection possible later
        # (drop_probability, stall_after_s — see plan.md Phase 4).
        self.declare_parameter('publish_rate_hz', 5.0)
        publish_rate_hz = self.get_parameter('publish_rate_hz').value

        # State the node owns. Real GPS would come from hardware; here we
        # just hardcode a plausible starting position (MDRS-area, Utah).
        self.lat = 38.406400
        self.lon = -110.791200

        # *** A publisher needs ***: message type, topic name, and a QoS setting.
        # The plain integer `10` here is a placeholder queue depth — it
        # works, but lesson 2 replaces it with a real QoSProfile once
        # BEST_EFFORT-vs-RELIABLE actually matters for a lossy radio link.
        self.gps_pub = self.create_publisher(NavSatFix, '/rover/gps', 10)

        # create_timer(period_seconds, callback) is rclpy's way of saying
        # "run this repeatedly" — no manual while-loop or sleep() needed,
        # and it plays correctly with rclpy.spin()'s event loop below.
        period_s = 1.0 / publish_rate_hz

        # Message (.msg) → data exchanged between nodes. Two processes must agree on it byte-for-byte.
        # Parameter (declare_parameter) → a node's own tunable configuration, private to that process. Settable at launch (YAML/CLI) or live via ros2 param set, readable via ros2 param get — no message type involved at all, since it's never sent to anyone.
        self.create_timer(period_s, self.publish_gps)

    def publish_gps(self):
        """Timer callback: build a message, stamp it, publish it."""
        msg = NavSatFix()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'gps'
        msg.latitude = self.lat
        msg.longitude = self.lon
        msg.altitude = 0.0
        self.gps_pub.publish(msg)


def main(args=None):
    # Every rclpy program follows this same three-step shape: init the ROS
    # context, spin a node until something stops it, then clean up. You'll
    # see this exact block, unchanged, at the bottom of the real sim node.
    rclpy.init(args=args)
    node = MinimalRoverNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
