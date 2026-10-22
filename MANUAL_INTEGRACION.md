# Manual de integración

Cómo poner el CAPTCHA lógico visual delante de cualquier programa en Python.

Hay una versión en PDF de este manual en [docs/Manual_Integracion_CAPTCHA.pdf](docs/Manual_Integracion_CAPTCHA.pdf).

## La función que se usa

```python
verificar_acceso(anunciar_acceso: bool = True) -> bool
```

Abre la ventana del CAPTCHA y **bloquea la ejecución hasta que termina**:

- Devuelve `True` si el usuario ganó la serie.
- Devuelve `False` si cerró la ventana, si quedó bloqueado y cerró, o si el CAPTCHA no se pudo cargar.

Si `anunciar_acceso` es `True`, después de "Validación completada correctamente" se muestra también el mensaje "Acceso concedido". Pásalo en `False` cuando tu programa ya tenga su propia bienvenida.

## Opción 1: importar `captcha.py` (recomendada)

1. Copia `captcha.py` en la misma carpeta que tu programa.
2. Llama a `verificar_acceso()` al inicio, **antes de crear tu ventana o de hacer cualquier cosa protegida**.

### Programa con Tkinter

```python
import sys
import tkinter as tk

from captcha import verificar_acceso

if not verificar_acceso():
    sys.exit(0)

root = tk.Tk()
root.title("Mi aplicación")
tk.Label(root, text="Contenido protegido").pack(padx=40, pady=40)
root.mainloop()
```

### Programa con función `main`

```python
from captcha import verificar_acceso


def main() -> None:
    if not verificar_acceso(anunciar_acceso=False):
        print("Acceso denegado.")
        return

    print("Bienvenido al sistema.")
    # ... resto del programa


if __name__ == "__main__":
    main()
```

También sirve para programas de consola, Pygame u otra interfaz gráfica. El CAPTCHA abre y cierra su propia ventana y después le devuelve el control a tu código.

### Si `captcha.py` está en una subcarpeta

```text
mi_proyecto/
├── app.py
└── seguridad/
    └── captcha.py
```

```python
from seguridad.captcha import verificar_acceso
```

## Opción 2: pegarlo dentro de tu archivo (entregar un solo `.py`)

Usa esta opción cuando quieras entregar un único archivo sin depender de `captcha.py`.

1. Pon `from __future__ import annotations` en la **primera línea** de tu archivo. Python exige que vaya antes que cualquier otro import.
2. Agrega los imports que usa el CAPTCHA y que tu archivo todavía no tenga:

   ```python
   import base64
   import json
   import math
   import secrets
   import sys
   import tkinter as tk
   from collections.abc import Callable
   from datetime import datetime, timedelta
   from io import BytesIO
   from pathlib import Path
   from tkinter import messagebox

   try:
       from PIL import Image, ImageTk
   except ImportError:
       Image = None
       ImageTk = None
   ```

3. Copia de `captcha.py` las constantes (desde `TITULO_CAPTCHA` hasta `AZAR`), las clases `GestorBloqueo`, `PartidaCaptcha` y `CaptchaApp`, las funciones `cargar_imagenes()` y `verificar_acceso()`, y el bloque `IMAGENES_CAPTCHA` completo.
   No copies `ProtectedApp`, `main()` ni el `if __name__ == "__main__":`.
4. Pega todo eso **antes** de la línea donde se crea tu ventana principal y agrega la verificación justo después:

   ```python
   # ... código del CAPTCHA pegado aquí, con IMAGENES_CAPTCHA al final ...

   if not verificar_acceso():
       sys.exit(0)

   root = tk.Tk()
   # ... tu programa sigue igual
   ```

   `IMAGENES_CAPTCHA` tiene que quedar **arriba** de la llamada a `verificar_acceso()`. Si la llamada está a nivel de módulo, Python la ejecuta en el momento en que la lee.

5. Revisa que no haya choques de nombres. El CAPTCHA usa nombres como `FUENTE`, `NOMBRES`, `AZAR`, `VENCE_A` y `cargar_imagenes`. Si tu programa ya usa alguno, renombra uno de los dos.

## Reglas importantes

- **Llámalo antes de crear tu propio `tk.Tk()`.** El CAPTCHA crea y destruye su propia ventana raíz. Si tu ventana ya existiera, el usuario podría verla y usarla mientras resuelve el CAPTCHA, y eso le quita el sentido a la puerta de acceso.
- **Llámalo desde el hilo principal.** Tkinter no funciona bien desde otros hilos.
- **El bloqueo se guarda junto al archivo** que contiene el CAPTCHA, en `data/lock_state.json`. Es junto a `captcha.py` si usas la opción 1, o junto a tu archivo si usas la opción 2. Si varios programas comparten esa carpeta, también comparten el bloqueo.
- **No hace falta copiar imágenes.** Van dentro del código.

## Personalización

Cambia las constantes al inicio del CAPTCHA:

```python
TIEMPO_RONDA = 20                          # segundos por ronda
DURACION_BLOQUEO = timedelta(seconds=50)   # duración del bloqueo
ACIERTOS_PARA_VALIDAR = 2
ERRORES_PARA_BLOQUEAR = 2
```

### Cambiar una imagen

Las imágenes son PNG en base64 dentro del diccionario `IMAGENES_CAPTCHA`, con las claves `"piedra"`, `"papel"` y `"tijeras"`. Para reemplazar una:

```python
import base64

with open("mi_imagen.png", "rb") as archivo:
    print(base64.b64encode(archivo.read()).decode())
```

Pega el texto que imprime en la clave que corresponda. Se recomienda un tamaño de hasta 420×270 píxeles. Con Pillow, cualquier tamaño se ajusta solo. Sin Pillow, Tkinter solo puede reducir la imagen por factores enteros.

## Solución de problemas

| Síntoma | Causa y solución |
|---------|------------------|
| `ModuleNotFoundError: No module named 'captcha'` | `captcha.py` no está en la misma carpeta que el programa que ejecutas. |
| "No fue posible cargar el CAPTCHA" | Una imagen de `IMAGENES_CAPTCHA` está incompleta o dañada. Vuelve a copiar el bloque completo. |
| Queda bloqueado al probar | Espera los 50 segundos o borra `data/lock_state.json`. |
| `No module named '_tkinter'` (Linux) | Instala Tkinter con `sudo apt install python3-tk`. |
| El programa se cierra al cerrar el CAPTCHA | Es lo esperado: `verificar_acceso()` devolvió `False` y tu código llamó a `sys.exit(0)`. |
