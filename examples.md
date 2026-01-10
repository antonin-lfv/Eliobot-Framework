# Fire

```py
eye_matrix_t0, eye_matrix_t1 = get_eyes_matrices()
matrix.set_matrix_colors(eye_matrix_t0)
time.sleep(0.5)

matrix.set_matrix_colors(eye_matrix_t1)
time.sleep(0.5)
```

# Cligner des yeux

```py
matrix.set_matrix_logo(matrix.emotionOpenedEyes, LED_COLOR)

time.sleep(3)

matrix.set_matrix_logo(matrix.emotionClosedEyes, LED_COLOR)

time.sleep(0.25)
```