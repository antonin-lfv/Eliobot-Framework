import time
import board
import pwmio
import analogio
import digitalio
import json
import wifi
import neopixel
from os import getenv
from adafruit_httpserver import Server, Request, FileResponse, Response, JSONResponse
import socketpool
from elio import Motors, Buzzer, ObstacleSensor, LineSensor, IRRemote, EyesMatrix
from utils import *

matrix = EyesMatrix(board.IO2)
buzzer = Buzzer(pwmio.PWMOut(board.IO17, variable_frequency=True))

LED_COLOR = (87, 49, 150)

# ----- setup des moteurs
AIN1 = pwmio.PWMOut(board.IO36)
AIN2 = pwmio.PWMOut(board.IO38)
BIN1 = pwmio.PWMOut(board.IO35)
BIN2 = pwmio.PWMOut(board.IO37)
vBatt_pin = analogio.AnalogIn(board.BATTERY)
motors = Motors(AIN1, AIN2, BIN1, BIN2, vBatt_pin)

# ----- setup capteurs d'obstacles
obstacleInput = [analogio.AnalogIn(pin) for pin in (board.IO4, board.IO5, board.IO6, board.IO7)]
obstacleSensor = ObstacleSensor(obstacleInput)
# 0 : capteur avant gauche; 1 : capteur avant; 2 : capteur avant droit; 3 : capteur arrière

# ----- setup capteurs de ligne
lineCmd = digitalio.DigitalInOut(board.IO33)
lineCmd.direction = digitalio.Direction.OUTPUT
lineInput = [analogio.AnalogIn(pin) for pin in (board.IO10, board.IO11, board.IO12, board.IO13, board.IO14)]
with open("config.json", "r") as f:
    calibration = json.load(f)
seuil = calibration["line_threshold"]
lineSensor = LineSensor(lineInput, lineCmd, motors)

# ----- setup de la LED
pixels = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2, auto_write=False, pixel_order=neopixel.GRB)

# ----- STARTUP SEQUENCE -----
print("Starting up...")
buzzer.sound_startup()

while True:    

    matrix.set_matrix_logo(matrix.emotionConfused, LED_COLOR)
    motors.move_forward()
    
    if obstacleSensor.get_obstacle(0):
        # Avant gauche
        motors.motor_stop()
        buzzer.sound_bump()
        print("obstacle 0 detected")
        matrix.set_matrix_logo(matrix.arrowRight, LED_COLOR)
        motors.turn_in_place(direction="left")
        time.sleep(1)
        matrix.clear_matrix()
    
    elif obstacleSensor.get_obstacle(1):
        # Avant
        motors.motor_stop()
        buzzer.sound_bump()
        print("obstacle 1 detected")
        matrix.set_matrix_logo(matrix.arrowDown, LED_COLOR)
        motors.move_backward()
        motors.turn_in_place(direction="right")
        time.sleep(1)
        matrix.clear_matrix()
    
    elif obstacleSensor.get_obstacle(2):
        # Avant droit
        motors.motor_stop()
        buzzer.sound_bump()
        print("obstacle 2 detected")
        matrix.set_matrix_logo(matrix.arrowLeft, LED_COLOR)
        motors.turn_in_place(direction="right")
        time.sleep(1)
        matrix.clear_matrix()
    
    elif obstacleSensor.get_obstacle(3):
        # Arrière
        motors.motor_stop()
        buzzer.sound_bump()
        print("obstacle 3 detected")
        matrix.set_matrix_logo(matrix.arrowUp, LED_COLOR)
        motors.move_forward()
        time.sleep(1)
        matrix.clear_matrix()
