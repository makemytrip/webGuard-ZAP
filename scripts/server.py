# Copyright 2017 MakeMyTrip (Kunal Aggarwal, Avinash Jain)
#
# This file is part of WebGuard.
#
# WebGuard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# WebGuard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with WebGuard.  If not, see <http://www.gnu.org/licenses/>.

import asyncore
import socket
import time
from threading import Thread
import subprocess
import uuid
from random import randint
from datetime import datetime
import psutil
import json
import pexpect
from base64 import b64decode
import traceback

flag = False
zap_instances = {}
HOME_DIR = "/opt/zap-server"

class EchoHandler(asyncore.dispatcher_with_send):
    global flag
    global zap_instances
    global HOME_DIR
    def test(self, data):
	global flag
	while flag:
		print "Waiting"
		time.sleep(1)
	flag = True
	time.sleep(10)
	flag = False
	self.send("INVALID COMMAND")

    def send_to_thread(self, data):
	global flag
	global zap_instances
        global HOME_DIR
	print "%s - Got Command : %s" % (datetime.now(), data)
	data = data.split()
	command = data[0]
	if command == "START":
		while flag:
	                print "%s - Waiting for another ZAP Start" % datetime.now()
        	        time.sleep(1)
		print "%s - Generating Key" % datetime.now()
		flag = True
		api_key = str(uuid.uuid4())
		print "%s - Got API Key %s" % (datetime.now(), api_key)

		port = "0"
		print "%s - Looking for Port" % datetime.now()
		while port == "0":
			i = randint(20000, 30000)
			process = subprocess.Popen("netstat -ntpl | grep %s | wc -l" % i, stdout=subprocess.PIPE, stderr=None, shell=True)
                        output = process.communicate()[0].strip()
			if output == "0":
				port = i
		print "%s - Got Port %s" % (datetime.now(), port)

		process = subprocess.Popen('cp -f %s/hosts/hosts %s/hosts/%s' % (HOME_DIR, HOME_DIR, api_key), stdout=subprocess.PIPE, stderr=None, shell=True)
		output = process.communicate()[0].strip()

		child = pexpect.spawn('unshare --mount')
		child.sendline('mount %s/hosts/%s /etc/hosts --bind' % (HOME_DIR, api_key))
		child.sendline('nohup %s/zap/zap.sh -daemon -port %s -host 0.0.0.0 -config api.key=%s >%s/logs/%s_%s.log 2>%s/logs/%s_%s_err.log &' % (HOME_DIR, port, api_key, HOME_DIR, port, api_key, HOME_DIR, port, api_key))
		time.sleep(1)
		process = subprocess.Popen("ps -ef | grep zap | grep java | grep -v defunct | grep %s | grep -v grep" % (port), stdout=subprocess.PIPE, stderr=None, shell=True)
                output = process.communicate()[0].strip()
		output = output.split()
		pid = int(output[1])
		print "%s - ZAP Start issued with PID %s. Waiting..." % (datetime.now(), pid)
                output = "0"
                while output == "0":
			print "%s - Waiting for ZAP to start" % datetime.now()
                        process = subprocess.Popen("netstat -ntpl | grep %s | wc -l" % port, stdout=subprocess.PIPE, stderr=None, shell=True)
                        output = process.communicate()[0].strip()
                        time.sleep(1)
		print "%s - ZAP Started at Port %s with Key %s and PID %s" % (datetime.now(), port, api_key, pid)
		flag = False
		zap_instances[str(port)] = {"api_key": api_key, "pid": pid, "child": child}
		self.send("%s %s %s" % (port, api_key, pid))
	elif command == "HOSTS":
		try:
                        port = data[1]
                        print "%s - Client requested for hosts file refresh of ZAP on Port %s" % (datetime.now(), port)
                        instance = zap_instances[port]
                        cmd = "cat %s/hosts/%s" % (HOME_DIR, instance["api_key"])
                        print cmd
			process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=None, shell=True)
                        output = process.communicate()[0]
			self.send(json.dumps({"data": output, "status": True}))
		except Exception as e:
                        traceback.print_exc()
                        print e
                        self.send(json.dumps({"message": "INVALID COMMAND", "status": False}))
	elif command == "WRITE":
		try:
			port = data[1]
			hostsdata = b64decode(data[2])
			print "%s - Client requested for writing to hosts file refresh of ZAP on Port %s" % (datetime.now(), port)
			instance = zap_instances[port]
			child = instance['child']
			key = instance['api_key']
			process = subprocess.Popen("echo '%s' > %s/hosts/%s" % (hostsdata, HOME_DIR, key), stdout=subprocess.PIPE, stderr=None, shell=True)
                        output = process.communicate()[0].strip()
			print "%s - Client requested for hosts file refresh of ZAP on Port %s" % (datetime.now(), port)
			child.sendline('umount %s/hosts/%s' % (HOME_DIR, key))
			child.sendline('mount %s/hosts/%s /etc/hosts --bind' % (HOME_DIR, key))
			self.send(json.dumps({"message": "Hosts File refreshed", "status": True}))
		except Exception as e:
			print e
			self.send(json.dumps({"message": "INVALID COMMAND", "status": False}))
	elif command == "STATUS":
		try:
			port = data[1]
			print "%s - Client asking for status of ZAP on Port %s" % (datetime.now(), port)
			instance = zap_instances[port]
			instance['handle'] = str(instance['handle'])
			self.send(json.dumps(instance))
		except:			
			self.send(json.dumps({"message": "INVALID COMMAND", "status": False}))
	elif command == "STOP":
		try:
			port = data[1]
			instance = zap_instances[port]
			print "%s - Stopping ZAP on Port %s" % (datetime.now(), port)
			child = instance['child']
			key = instance['api_key']
			child.sendline('umount %s/hosts/%s' % (HOME_DIR, key))
			process = subprocess.Popen("kill -9 %s" % (instance['pid']), stdout=subprocess.PIPE, stderr=None, shell=True)
	                output = process.communicate()[0].strip()
			child.kill(9)
			del zap_instances[port]
			self.send(json.dumps({"message": "Stopped ZAP on Port %s with PID %s" % (port, instance['pid']), "status": True}))
		except:
			self.send(json.dumps({"message": "INVALID COMMAND", "status": False}))
	elif command == "HEALTH":
                try:
                        port = data[1]
                        instance = zap_instances[port]
                        print "%s - Checking health of ZAP on Port %s" % (datetime.now(), port)
                        pid = instance['pid']
			process = subprocess.Popen("ps -ef | grep %s | grep java | grep -v defunct | grep -v grep | wc -l" % (pid), stdout=subprocess.PIPE, stderr=None, shell=True)
			output = process.communicate()[0].strip()
			if output == "1":
				self.send(json.dumps({"status": True}))
			elif output == "0":
				self.send(json.dumps({"status": False}))
                except:
			self.send(json.dumps({"message": "INVALID COMMAND", "status": False}))
	elif command == "STATS":
		total = psutil.virtual_memory().total >> 20
		free  = psutil.virtual_memory().free >> 20
		used  = total - free
		perc  = (float(free) / float(total)) * 100
		print "%s - Sending Memory Stats" % (datetime.now())
		self.send('{"total": %s, "used": %s, "free": %s, "percentage": %s}' % (total, used, free, perc))
	elif command == "PING":
		self.send('PONG')
	else:
		self.send(json.dumps({"message": "INVALID COMMAND", "status": False}))

    def handle_read(self):
        data = self.recv(8192)
        if data:
		t = Thread(target = self.send_to_thread, args = (data,))
		t.start()

class EchoServer(asyncore.dispatcher):

    def __init__(self, host, port):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host, port))
        self.listen(50)

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            sock, addr = pair
            print '%s - Incoming connection from %s' % (datetime.now(), repr(addr))
            handler = EchoHandler(sock)

server = EchoServer('0.0.0.0', 30115)
print "-" * 50
print "SERVER STARTUP"
print "-" * 50
print "%s - Listening on 0.0.0.0:30115" % datetime.now()
asyncore.loop()
