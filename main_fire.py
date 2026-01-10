import time
import board
import pwmio
import analogio
import digitalio
import json
import wifi
import neopixel
from os import getenv
import socketpool
from utils import *
from elio import Motors, Buzzer, ObstacleSensor, LineSensor, IRRemote, EyesMatrix

matrix = EyesMatrix(board.IO2)
buzzer = Buzzer(pwmio.PWMOut(board.IO17, variable_frequency=True))

print("Starting up...")
buzzer.sound_startup()


while True:    
    eye_matrix_t0, eye_matrix_t1 = get_eyes_matrices()
    matrix.set_matrix_colors(eye_matrix_t0)
    time.sleep(0.5)
    matrix.set_matrix_colors(eye_matrix_t1)
    time.sleep(0.5)