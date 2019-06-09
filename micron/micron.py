#!/usr/bin/env python3
# hashbang but it's meant to be run on windows ._.

# Python Helper to interact with the NanoLab Microcontroller
# Microcontroller Model: Micos 1860SMC Basic
# Made 2019, Sun Yudong
# sunyudong [at] outlook [dot] sg

# IMPT: THIS IS A HELPER FILE
# RUNNING IT DIRECTLY YIELDS INTERACTIVE TERMINAL

import serial
import sys, os
import time
import signal
import json

import shutter

class Stage():
    def __init__(self, stageAsDict = None):
        # WARNING: THIS IS A STATIC OBJECT THAT DOES NOT DO ANY STAGE MANIPULATION
        # IF EXCEPTIONS INVOLVING THE STAGE MUST BE HANDLED, PLEASE HANDLE BEFORE PASSING TO THIS

        # set some default values
        # we assume stage is initialized (homed)

        # currently only supports 2-axis. To extend to 3 axis, adjust where appropriate

        # stageAsDict = property -> value
        # e.g.  { "xlim" : [-5,5] } etc.

        # Set xlim and ylim to be 2 identical value for it to automatically find the range (USE WITH CAUTION)

        self.xlim = [-10000, 0]
        self.ylim = [-10000, 0]
        self.x    = 0
        self.y    = 0

        if stageAsDict:
            self.update(stageAsDict)

    def __repr__(self):
        return "Stage <x [{},{}], y [{},{}]>".format(self.xlim[0], self.xlim[1], self.ylim[0], self.ylim[1])

    def update(self, stageAsDict):
        for k, v in stageAsDict.items():
            if k.endswith("lim") and type(v) is not list:
                raise TypeError("Limit must be a list [lower, upper]")
            setattr(self, k, v)

    def setpos(self, x, y):
        # We keep track of our own coordinates
        # Coordinates replied from the stage is not very consistent
        self.x = x
        self.y = y

class Micos():
	def __init__(self, stageConfig = None, noCtrlCHandler = False):
		# stageConfig can be a dictionary or a json filename
		# See self.help for documentation

		cfg = {
			"port"      : "COM1",
			"baudrate"  : 9600, #19200,
			"parity"    : serial.PARITY_NONE,
			"stopbits"  : serial.STOPBITS_ONE,
			"bytesize"  : serial.EIGHTBITS,
			"timeout"   : 2
		}

		self.ENTER = b'\x0D' #chr(13)  # CR

		self.stage = Stage()
		if stageConfig: 
			if type(stageConfig) is str:
				with open(stageConfig, 'r') as f:
					stageConfig = json.load(f)
			
			self.stage.update(stageConfig)

		self.units = { "microstep": 0,  "um": 1, "mm": 2, "cm": 3, "m": 4, "in": 5, "mil": 6 }

		try:
			self.dev = serial.Serial(
					port 		= cfg['port'],
					baudrate 	= cfg['baudrate'],
					parity 		= cfg['parity'],
					stopbits    = cfg['stopbits'],
					bytesize    = cfg['bytesize'],
					timeout     = cfg['timeout']
				)
			if self.dev.isOpen():
				self.dev.close()
				self.dev.open()

			time.sleep(2)
			print("Initalised serial communication...")

			if not noCtrlCHandler: self.startInterruptHandler()

			self.shutter = shutter.Shutter()
			self.initialize()

		except Exception as e:
			print(e)
			print("Unable to establish serial communication. Please check port settings and change configuration file accordingly. For more help, consult the documention.")
			sys.exit(0)

	def startInterruptHandler(self):
		# https://stackoverflow.com/a/4205386/3211506
		signal.signal(signal.SIGINT, self.KeyboardInterruptHandler)

	def KeyboardInterruptHandler(self, signal, frame):
		print("^C Detected: Aborting the FIFO stack and closing port.")
		print("Shutter will be closed as part of the aborting process.")
		x.abort()
		x.dev.close()
		print("Exiting")
		sys.exit(1)
		# use os._exit(1) to avoid raising any SystemExit exception

	def initialize(self):
		print("Stage Initialization...", end="\r")
		self.setunits()
		self.homeStage()
		print("Stage Initialization Finished")

	def homeStage(self):
		# return x.send("cal") 		# DO NOT USE CAL ON RUDOLPH => there are some physical/mechanical issues
		xl = abs(self.stage.xlim[1] - self.stage.xlim[0])
        yl = abs(self.stage.ylim[1] - self.stage.ylim[0])

		if xl > 0 and yl > 0:
			self.send("rm") 			# send to maximum
			self.setpos(0, 0)
            self.setlimits(self.stage.xlim[0], self.stage.ylim[0], self.stage.xlim[1], self.stage.ylim[1])
			self.rmove(x = -xl/2, y = -yl/2)
		else:
			raise NotImplementedError("Setting the limits to zero asks the script to find the limits of the stage, which is not implemented yet.")
			# UNTESTED CODE
			# self.send("cal")
			# self.setpos(0, 0)
			# self.send("rm")
			# q = self.getpos()

	def rmove(self, x, y):
        try:
            self.stage.setpos(self.stage.x + x, self.stage.y + y) # Note this is not Micos.setpos
            return self.send("{} {} r".format(x, y))
        except:
            pass

    def move(self, x, y):
    	try:
    		raise RuntimeWarning("This function may not work as intended. Please use with caution.")
            self.stage.setpos(x, y) # Note this is not Micos.setpos
            return self.send("{} {} m".format(x, y))
        except:
            pass

	def setpos(self, x, y):
        self.stage.setpos(x, y)
		return self.send("{} {} setpos".format(x, y))

	def getpos(self):
        # IMPT THIS DOES NOT UPDATE INTERNAL TRACKING COORDS
		# returns the position as reported by the stage in the form of [x, y]
        # Empty split will split by whitespace
		return self.send("p", waitClear = True).strip().split()

	def setlimits(self, xmin, ymin, xmax, ymax):
		# -A1, -A2, +A1, +A2
		# ' '.join("'{0}'".format(n) for n in limits)
		self.stage.update({
				"xlim": [xmin, xmax],
				"ylim": [ymin, ymax]
			})
		return self.send("{} {} {} {} setlimit".format(xmin, ymin, xmax, ymax))

	def setunits(self, unit = "um"):
		# 0 = microstep = 1 motor revolution / 40000 steps, 1 = set to um, 2 = mm, 3 = cm, 4 = m, 5 = in, 6 = mil = 1/1000in

		un = self.units.get(unit, 1) # default to um
		self.send("{} 1 setunit".format(un)) # x-axis
		self.send("{} 2 setunit".format(un)) # y-axis
		self.send("{} 0 setunit".format(un)) # velocity

		return self.send("ge")

	def send(self, cmd, waitClear = False, raw = False):
		# Writes cmd to the serial channel, returns the data as a list
		cmd = cmd.encode("ascii") + self.ENTER if not raw else cmd

		if waitClear: self.waitClear()

		self.dev.write(cmd)

		return self.read()

	def read(self):
		time.sleep(1)

		out = b''
		while self.dev.inWaiting() > 0:
			out += self.dev.read(1)

		return out.strip() if len(out) else None

	def waitClear(self):
		# we wait until all commands are done running and the stack is empty
		while self.getStatus(0):
			print("Waiting for stack to clear...", end="\r")
			time.sleep(1)
		print("Waiting for stack to clear...cleared")

		return True

	def getStatus(self, digit = None):
		# Get the status of the controller

		self.dev.write("st".encode("ascii") + self.ENTER)
		time.sleep(1)
		x = int(self.read())

		if digit is None:
			# we return the full status in a string of binary digits
			return bin(x)[2:]
		else:
			# generate bitmask
			mask = 1 << digit
			return (x & mask)

		# LSB
		# D0  1   Status current command execution
		# D1  2   Status Joystick or Handwheel
		# D2  4   Status Button A
		# D3  8   Machine Error
		# D4  16  Status speed mode
		# D5  32  Status In-Window
		# D6  64  Status setinfunc
		# D7  128 Status motor enable, safety device
		# D8  256 Joystick button
		# MSB

	def abort(self, closeShutter = True):
		# return x.send("abort")
		# Send Ctri + C + self.Enter
		self.send(b"\x03\x0D", raw=True)

		if closeShutter:
			self.shutter.close()

	def getError(self):
		return self.send("ge", waitClear=True)

	def help(self):
		self.dipswitches = {
			1: "Baudrate Switch",
			2: "Baudrate Switch",
				# Baudrate apparently determined by Dip-Switch 1 and 2
				# I referenced the manual for Corvus, but I suspect this model is different
				# It works for now and I can't care enough to experiment
				# DS1 DS2
				# 0   0    9600
				# 0   1    19200
				# 1   0    57600
				# 1   1    115200
			3: "Closed Loop On/Off",
			6: "ON = Terminal Mode; OFF = Host Mode",
				# Terminal Mode returns the actual coordinates immediately
				# Host Mode only returns data when asked
		}

	def __enter__(self):
		return self

	def __exit__(self, e_type, e_val, traceback):
		# self.abort()
		self.dev.close()

if __name__ == '__main__':
	with Micos() as m:
		print("m = Micos()\n\n")
		# import pdb; pdb.set_trace()
		import code; code.interact(local=locals())