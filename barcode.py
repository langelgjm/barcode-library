#!/usr/bin/python

import sys
import serial

def main():
	try:
		ser = serial.Serial('/dev/ttyACM0', 9600)
		while True:
			barcode = ser.readline()
			barcode = barcode.strip()
			print barcode
	except KeyboardInterrupt:
		ser.close()
		sys.exit()

if __name__ == "__main__":
    main()
