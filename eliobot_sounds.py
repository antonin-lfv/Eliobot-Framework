import time
import pwmio
import board
import random

buzzer = pwmio.PWMOut(board.IO17, duty_cycle=0, frequency=440, variable_frequency=True)

def play(freq, dur, pause=0.01):
    buzzer.frequency = int(freq)
    buzzer.duty_cycle = 32768
    time.sleep(dur)
    buzzer.duty_cycle = 0
    time.sleep(pause)

def sweep(start, end, dur, steps=10):
    step_dur = dur / steps
    step_freq = (end - start) / steps
    for i in range(steps):
        play(start + step_freq * i, step_dur)

### 🎵 12 sons Eliobot ###

def sound_jump():
    sweep(600, 1300, 0.2, 12)

def sound_laser():
    sweep(1600, 300, 0.15, 10)

def sound_question():
    play(900, 0.1)
    play(1100, 0.05)
    play(700, 0.15)

def sound_error():
    play(300, 0.2)
    play(250, 0.2)

def sound_explosion():
    for i in range(18):
        f = 1200 - i * 60 + random.randint(-30, 30)
        play(f, 0.015)

def sound_land():
    sweep(1000, 400, 0.3, 15)
    play(200, 0.1)

def sound_happy():
    play(1000, 0.05)
    play(1300, 0.05)
    play(1600, 0.1)
    play(1300, 0.05)
    play(1700, 0.2)

def sound_win():
    play(1000, 0.1)
    play(1300, 0.1)
    play(1700, 0.15)
    play(2000, 0.2)

def sound_alert():
    for i in range(6):
        play(1800 if i % 2 == 0 else 1400, 0.05)

def sound_hello():
    sweep(900, 1200, 0.15, 5)
    play(1100, 0.1)
    sweep(1200, 800, 0.15, 5)

def sound_startup():
    sweep(500, 1500, 0.3, 12)
    play(1800, 0.1)
    play(1500, 0.1)

def sound_bump():
    play(800, 0.05)
    play(500, 0.05)
    play(300, 0.15)
    
def sound_blink():
    play(1000, 0.03)
    play(1300, 0.03)
    play(1600, 0.05)

def melody_robot_peur():
    play(146.83, 0.25)  # ré3
    play(174.61, 0.25)  # fa3
    play(196.00, 0.40)  # sol3
    time.sleep(0.15)    # pause
    play(207.65, 0.20)  # sol#3
    play(220.00, 0.30)  # la3
    time.sleep(0.20)    # pause
    play(73.42,  0.50)  # ré2 (grave)
    
def melody_hmm():
    play(261.63, 0.40)  # do4
    play(293.66, 0.30)  # ré4
    play(329.63, 0.50)  # mi4
    play(329.63, 0.30)  # mi4
    play(293.66, 0.25)  # ré4
    play(261.63, 0.60)  # do4
    
def melody_alert():
    play(440.00, 0.20)  # la4
    play(440.00, 0.20)  # la4
    play(440.00, 0.20)  # la4
    play(349.23, 0.30)  # fa4
    play(392.00, 0.40)


def sound_error():
    play(300, 0.20, 0.02)
    play(250, 0.20, 0.02)
    
def emotion_joie():
    for _ in range(2):
        play(660, 0.12, 0.02)  # E5
        play(784, 0.12, 0.02)  # G5
        play(880, 0.18, 0.03)  # A5
        time.sleep(0.06)
    play(1046, 0.28, 0.06)
    
def emotion_colere():
    for i in range(6):
        play(150 + i * 5, 0.06, 0.02)   # pulse grave désaccordé légèrement
        time.sleep(0.02)

def emotion_surprise():
    play(1800, 0.08, 0.01)
    time.sleep(0.06)
    play(2000, 0.06, 0.01)
    time.sleep(0.12)
    play(1500, 0.10, 0.05)
    
def emotion_amour():
    play(440, 0.25, 0.02)   # A4
    play(523.25, 0.25, 0.02) # C5 (tierce)
    time.sleep(0.06)
    play(659.25, 0.40, 0.04) # E5
    time.sleep(0.08)
    play(523.25, 0.35, 0.04)
    
def emotion_degoût():
    for i in range(8):
        f = 300 + (i % 2) * 40 + random.randint(-15, 15)
        play(f, 0.05, 0.01)
    time.sleep(0.05)
    play(240, 0.25, 0.05)
    
def emotion_confusion():
    for i in range(10):
        f = random.choice([330, 370, 440, 520, 600])
        dur = random.choice([0.05, 0.08, 0.12])
        play(f + random.randint(-10, 10), dur, 0.02)
    time.sleep(0.06)
    play(280, 0.18, 0.04)
    
def melody_robot_peur():
    play(146.83, 0.25, 0.02)  # ré3
    play(174.61, 0.25, 0.02)  # fa3
    play(196.00, 0.40, 0.03)  # sol3
    time.sleep(0.15)          # pause
    play(207.65, 0.20, 0.02)  # sol#3
    play(220.00, 0.30, 0.03)  # la3
    time.sleep(0.20)
    play(73.42,  0.50, 0.05)  # ré2 (grave)
    
def endormi():
    base = 660
    for i in range(5):
        f = base - i*40 + (5 if i%2==0 else -5)
        play(f, 0.35, 0.06)
    time.sleep(0.12)
    # petite conclusion plus grave
    play(220, 0.6, 0.08)
    
def emotion_reveur():
    play(330, 0.35, 0.04)
    time.sleep(0.03)
    play(440, 0.45, 0.05)
    time.sleep(0.05)
    play(660, 0.55, 0.06)
    time.sleep(0.08)
    sweep(880, 720, 0.6, 10, 0.02)
    time.sleep(0.12)
    play(660, 0.55, 0.06)
    play(660, 0.55, 0.06)
    
def emotion_detente():

    play(160, 0.8, 0.06)   # hum grave et long
    time.sleep(0.06)
    sweep(200, 700, 0.9, 18, 0.01)
    time.sleep(0.12)
    
def melody_marseillaise():

    # Allons enfants de la Patrie
    play(392, 0.45)   # sol4
    play(392, 0.45)   # sol4
    play(440, 0.55)   # la4
    play(493.9, 0.55) # si4
    play(523.3, 0.75) # do5
    time.sleep(0.20)

    # Le jour de gloire est arrivé
    play(523.3, 0.45) # do5
    play(493.9, 0.45) # si4
    play(493.9, 0.45) # si4
    play(523.3, 0.55) # do5
    play(587.3, 0.75) # ré5
    play(523.3, 0.75) # do5
    time.sleep(0.20)

    # Contre nous de la tyrannie
    play(493.9, 0.45) # si4
    play(493.9, 0.45) # si4
    play(493.9, 0.45) # si4
    play(523.3, 0.55) # do5
    play(587.3, 0.60) # ré5
    play(659.3, 0.80) # mi5
    time.sleep(0.20)

    # L'étendard sanglant est levé !
    play(659.3, 0.45) # mi5
    play(659.3, 0.45) # mi5
    play(659.3, 0.45) # mi5
    play(587.3, 0.55) # ré5
    play(523.3, 0.55) # do5
    play(493.9, 0.80) # si4
