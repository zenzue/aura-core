# AURA face simulator

Static browser simulator of the Core2 face: canvas exactly 320x240,
parameters ported from `firmware/src/aura/anim/EmotionEngine.cpp`
(expression table, blink/gaze dynamics) and `firmware/src/aura/face/FaceRenderer.cpp`
(geometry: eye centers 104/216, y=106, halfW=34, halfH=40, RGB565 colors,
halo rings, lid-tilt split rects, iris/core/pupil/highlight).

Run:
```bash
./simulator/serve.sh   # then open http://127.0.0.1:8317
```

Buttons: 16 emotions (first 4 letters), speak amplitude slider, thinking toggle,
force blink, brightness. This is compile/sim-verified only; hardware verification
follows docs/hardware-verification.md.
