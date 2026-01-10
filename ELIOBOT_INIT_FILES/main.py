import board
import eliobot_sounds
from matrix import MatrixLED
import time 
matrix = MatrixLED(board.IO2)



matrixLeft = [
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,1,1,1,1,1,0,0,
    1,0,0,0,0,0,1,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
]

matrixRight = [
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,1,1,1,1,1,0,
    0,1,0,0,0,0,0,1,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0
]

# Couleur à appliquer
rgb_color = (87, 49, 150)

matrixFinal = matrixLeft + matrixRight 

# Application des couleurs
led_colors = [rgb_color if pixel == 1 else (0, 0, 0) for pixel in matrixFinal]
                  
matrix.set_matrix_colors(led_colors)



eliobot_sounds.sound_startup()


matrixLeft = [
    0,0,0,0,0,0,0,0,
    0,1,1,0,1,1,0,0,
    1,1,1,1,1,1,1,0,
    1,1,1,1,1,1,1,0,
    1,1,1,1,1,1,1,0,
    0,1,1,1,1,1,0,0,
    0,0,1,1,1,0,0,0,
    0,0,0,1,0,0,0,0
]

matrixRight = [
    0,0,0,0,0,0,0,0,
    0,0,1,1,0,1,1,0,
    0,1,1,1,1,1,1,1,
    0,1,1,1,1,1,1,1,
    0,1,1,1,1,1,1,1,
    0,0,1,1,1,1,1,0,
    0,0,0,1,1,1,0,0,
    0,0,0,0,1,0,0,0
]

# Couleur à appliquer
rgb_color = (87, 49, 150)

matrixFinal = matrixLeft + matrixRight 

# Application des couleurs
led_colors = [rgb_color if pixel == 1 else (0, 0, 0) for pixel in matrixFinal]
                  
matrix.set_matrix_colors(led_colors)



time.sleep(3)


matrixLeft = [
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,1,1,1,1,1,0,0,
    1,0,0,0,0,0,1,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
]

matrixRight = [
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,1,1,1,1,1,0,
    0,1,0,0,0,0,0,1,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0
]

# Couleur à appliquer
rgb_color = (87, 49, 150)

matrixFinal = matrixLeft + matrixRight 

# Application des couleurs
led_colors = [rgb_color if pixel == 1 else (0, 0, 0) for pixel in matrixFinal]
                  
matrix.set_matrix_colors(led_colors)
eliobot_sounds.sound_blink()



time.sleep(0.015)

matrixLeft = [
    0,0,0,0,0,0,0,0,
    0,1,1,0,1,1,0,0,
    1,1,1,1,1,1,1,0,
    1,1,1,1,1,1,1,0,
    1,1,1,1,1,1,1,0,
    0,1,1,1,1,1,0,0,
    0,0,1,1,1,0,0,0,
    0,0,0,1,0,0,0,0
]

matrixRight = [
    0,0,0,0,0,0,0,0,
    0,0,1,1,0,1,1,0,
    0,1,1,1,1,1,1,1,
    0,1,1,1,1,1,1,1,
    0,1,1,1,1,1,1,1,
    0,0,1,1,1,1,1,0,
    0,0,0,1,1,1,0,0,
    0,0,0,0,1,0,0,0
]

# Couleur à appliquer
rgb_color = (87, 49, 150)

matrixFinal = matrixLeft + matrixRight 

# Application des couleurs
led_colors = [rgb_color if pixel == 1 else (0, 0, 0) for pixel in matrixFinal]
                  
matrix.set_matrix_colors(led_colors)



time.sleep(0.15)


matrixLeft = [
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,1,1,1,1,1,0,0,
    1,0,0,0,0,0,1,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
]

matrixRight = [
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,1,1,1,1,1,0,
    0,1,0,0,0,0,0,1,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0
]

# Couleur à appliquer
rgb_color = (87, 49, 150)

matrixFinal = matrixLeft + matrixRight 

# Application des couleurs
led_colors = [rgb_color if pixel == 1 else (0, 0, 0) for pixel in matrixFinal]
                  
matrix.set_matrix_colors(led_colors)
eliobot_sounds.sound_blink()



time.sleep(0.015)
    
    
while True:
    
    matrixLeft = [
        0,0,0,0,0,0,0,0,
        0,1,1,0,1,1,0,0,
        1,1,1,1,1,1,1,0,
        1,1,1,1,1,1,1,0,
        1,1,1,1,1,1,1,0,
        0,1,1,1,1,1,0,0,
        0,0,1,1,1,0,0,0,
        0,0,0,1,0,0,0,0
    ]

    matrixRight = [
        0,0,0,0,0,0,0,0,
        0,0,1,1,0,1,1,0,
        0,1,1,1,1,1,1,1,
        0,1,1,1,1,1,1,1,
        0,1,1,1,1,1,1,1,
        0,0,1,1,1,1,1,0,
        0,0,0,1,1,1,0,0,
        0,0,0,0,1,0,0,0
    ]

    # Couleur à appliquer
    rgb_color = (87, 49, 150)

    matrixFinal = matrixLeft + matrixRight 

    # Application des couleurs
    led_colors = [rgb_color if pixel == 1 else (0, 0, 0) for pixel in matrixFinal]
                      
    matrix.set_matrix_colors(led_colors)



    time.sleep(3)


    matrixLeft = [
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
        0,1,1,1,1,1,0,0,
        1,0,0,0,0,0,1,0,
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
    ]

    matrixRight = [
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
        0,0,1,1,1,1,1,0,
        0,1,0,0,0,0,0,1,
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0
    ]

    # Couleur à appliquer
    rgb_color = (87, 49, 150)

    matrixFinal = matrixLeft + matrixRight 

    # Application des couleurs
    led_colors = [rgb_color if pixel == 1 else (0, 0, 0) for pixel in matrixFinal]
                      
    matrix.set_matrix_colors(led_colors)
    
    
    
    time.sleep(0.15)
    
    matrixLeft = [
        0,0,0,0,0,0,0,0,
        0,1,1,0,1,1,0,0,
        1,1,1,1,1,1,1,0,
        1,1,1,1,1,1,1,0,
        1,1,1,1,1,1,1,0,
        0,1,1,1,1,1,0,0,
        0,0,1,1,1,0,0,0,
        0,0,0,1,0,0,0,0
    ]

    matrixRight = [
        0,0,0,0,0,0,0,0,
        0,0,1,1,0,1,1,0,
        0,1,1,1,1,1,1,1,
        0,1,1,1,1,1,1,1,
        0,1,1,1,1,1,1,1,
        0,0,1,1,1,1,1,0,
        0,0,0,1,1,1,0,0,
        0,0,0,0,1,0,0,0
    ]

    # Couleur à appliquer
    rgb_color = (87, 49, 150)

    matrixFinal = matrixLeft + matrixRight 

    # Application des couleurs
    led_colors = [rgb_color if pixel == 1 else (0, 0, 0) for pixel in matrixFinal]
                      
    matrix.set_matrix_colors(led_colors)



    time.sleep(0.15)


    matrixLeft = [
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
        0,1,1,1,1,1,0,0,
        1,0,0,0,0,0,1,0,
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
    ]

    matrixRight = [
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
        0,0,1,1,1,1,1,0,
        0,1,0,0,0,0,0,1,
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0
    ]

    # Couleur à appliquer
    rgb_color = (87, 49, 150)

    matrixFinal = matrixLeft + matrixRight 

    # Application des couleurs
    led_colors = [rgb_color if pixel == 1 else (0, 0, 0) for pixel in matrixFinal]
                      
    matrix.set_matrix_colors(led_colors)
    
    
    
    time.sleep(0.15)
    matrixLeft = [
        0,0,0,0,0,0,0,0,
        0,1,1,0,1,1,0,0,
        1,1,1,1,1,1,1,0,
        1,1,1,1,1,1,1,0,
        1,1,1,1,1,1,1,0,
        0,1,1,1,1,1,0,0,
        0,0,1,1,1,0,0,0,
        0,0,0,1,0,0,0,0
    ]

    matrixRight = [
        0,0,0,0,0,0,0,0,
        0,0,1,1,0,1,1,0,
        0,1,1,1,1,1,1,1,
        0,1,1,1,1,1,1,1,
        0,1,1,1,1,1,1,1,
        0,0,1,1,1,1,1,0,
        0,0,0,1,1,1,0,0,
        0,0,0,0,1,0,0,0
    ]

    # Couleur à appliquer
    rgb_color = (87, 49, 150)

    matrixFinal = matrixLeft + matrixRight 

    # Application des couleurs
    led_colors = [rgb_color if pixel == 1 else (0, 0, 0) for pixel in matrixFinal]
                      
    matrix.set_matrix_colors(led_colors)

