# CAPTCHA Lógico Visual: Piedra, Papel o Tijeras

CAPTCHA de escritorio hecho en Python con Tkinter. Para distinguir a una persona de un programa automatizado combina tres cosas: reconocer una imagen, aplicar la regla de Piedra, Papel o Tijeras y responder dentro de un tiempo límite.

Se usa como puerta de acceso. La aplicación protegida solo se abre si el usuario supera el desafío. Si lo cierra o falla, el acceso se niega.

## Cómo funciona

1. La ventana muestra **mi opción**: una de las tres imágenes, elegida al azar.
2. Debajo aparecen tres botones con **las tres imágenes** en un orden distinto en cada ronda.
3. El usuario tiene que pulsar la imagen que **le gana** a la mostrada.

| Imagen mostrada | Respuesta correcta |
|-----------------|--------------------|
| Piedra          | Papel              |
| Papel           | Tijeras            |
| Tijeras         | Piedra             |

Las imágenes son símbolos híbridos que una persona reconoce sin problema, pero que son visualmente complejos:

- **Piedra:** un puño cerrado hecho de ladrillos.
- **Papel:** una mano abierta fusionada con un paso peatonal.
- **Tijeras:** la seña de tijera cubierta de patrones ópticos y geométricos.

### Reglas de la serie

- **Formato:** se juega al mejor de tres, con **15 segundos por ronda** y una cuenta regresiva visible.
- **Qué cuenta como error:** una respuesta incorrecta, un empate (elegir el mismo símbolo) o que se acabe el tiempo.
- **Respuesta visual:** el botón elegido se pinta de verde o de rojo junto con un mensaje, y la siguiente ronda empieza 1 segundo después.
- **Con 2 aciertos:** aparece "Validación completada correctamente" y luego "Acceso concedido".
- **Con 2 errores:** el acceso queda **bloqueado 50 segundos**. La pantalla muestra una cuenta regresiva (50, 49, 48… 0) y al llegar a cero empieza una serie nueva.
- **Persistencia:** el bloqueo se guarda en disco, así que cerrar y volver a abrir el programa no lo evita.
- **Cerrar la ventana** del CAPTCHA equivale a negar el acceso.

## Requisitos

- Python 3.8 o superior (probado con Python 3.13).
- Tkinter, que ya viene con el instalador oficial de Python para Windows. En Linux se instala con `sudo apt install python3-tk`.
- Pillow es **opcional**. Si está instalado, las imágenes se escalan con mejor calidad. Si no, se usa el lector PNG de Tkinter.

```bash
pip install pillow
```

No se necesita ningún otro archivo. Las imágenes van embebidas en `captcha.py` como PNG en base64.

## Ejecución

```bash
python captcha.py
```

Al superar el CAPTCHA se abre una ventana de demostración llamada **Área Protegida**.

El programa funciona igual desde VS Code (botón Run o Code Runner), IDLE, PyCharm o la terminal. Las rutas se calculan a partir de la ubicación del archivo y no de la carpeta desde donde se ejecuta.

## Integrarlo en otro programa

```python
import sys
from captcha import verificar_acceso

if not verificar_acceso():
    sys.exit(0)

# ... aquí arranca tu programa
```

Los detalles, los ejemplos y la opción de pegarlo dentro de un solo archivo están en el [manual de integración](MANUAL_INTEGRACION.md).

## Configuración

Las reglas están en constantes al inicio de `captcha.py`:

| Constante               | Valor                  | Descripción                                          |
|-------------------------|------------------------|------------------------------------------------------|
| `TIEMPO_RONDA`          | `15`                   | Segundos por ronda (el enunciado permite usar 20).   |
| `ACIERTOS_PARA_VALIDAR` | `2`                    | Rondas ganadas para validar.                         |
| `ERRORES_PARA_BLOQUEAR` | `2`                    | Errores que activan el bloqueo.                      |
| `DURACION_BLOQUEO`      | `timedelta(seconds=50)`| Duración del bloqueo temporal.                       |
| `PAUSA_ENTRE_RONDAS_MS` | `1000`                 | Pausa para mostrar el resultado antes de seguir.     |
| `ANCHO_VENTANA` / `ALTO_VENTANA` | `1000` / `700` | Tamaño de la ventana.                               |

`RONDAS_MAXIMAS` no se configura a mano. Se calcula a partir de los aciertos y los errores (2 + 2 − 1 = 3).

## Persistencia del bloqueo

El bloqueo se guarda en `data/lock_state.json`, junto a `captcha.py`. La carpeta se crea sola la primera vez que alguien queda bloqueado.

```json
{
    "locked_until": "2026-10-22T16:45:00"
}
```

- **Al iniciar:** se revisa si el archivo existe y si el bloqueo sigue vigente.
- **Si ya venció:** el archivo se borra.
- **Si está dañado:** se ignora y el programa no se cae.
- **Si la fecha guardada supera la duración configurada:** se recorta a 50 segundos desde ese momento y se vuelve a guardar. Esto puede pasar con un archivo de una configuración anterior más larga o si se atrasó el reloj del sistema.
- **Para quitar el bloqueo durante pruebas:** borra ese archivo.

## Estructura del código

| Elemento            | Responsabilidad |
|---------------------|-----------------|
| `GestorBloqueo`     | Leer, guardar y levantar el bloqueo en `data/lock_state.json`. |
| `PartidaCaptcha`    | Llevar el marcador de la serie (ronda, aciertos, errores), sin nada de interfaz. |
| `CaptchaApp`        | La ventana: imagen central, botones, temporizador, mensajes y pantalla de bloqueo. |
| `ProtectedApp`      | La ventana de demostración "Área Protegida". |
| `cargar_imagenes()` | Decodificar las imágenes embebidas y ajustarlas al tamaño de cada zona. |
| `verificar_acceso()`| El punto de entrada: muestra el CAPTCHA y devuelve `True` solo si se superó. |
| `IMAGENES_CAPTCHA`  | Las tres imágenes en PNG codificadas en base64. |

## Mecanismos de seguridad simulada

| Mecanismo               | Implementación |
|-------------------------|----------------|
| Desafío visual          | Imágenes híbridas con patrones complejos. |
| Desafío lógico          | Hay que elegir la opción que **le gana** a la mostrada, no la que es igual. |
| Temporizador            | 15 segundos por ronda; si se acaba, cuenta como error. |
| Aleatorización          | El símbolo y el orden de los botones cambian en cada ronda, usando `secrets.SystemRandom`. |
| Limitación de intentos  | Con 2 errores se termina la serie. |
| Bloqueo temporal        | 50 segundos con cuenta regresiva visible. |
| Persistencia de sanción | El bloqueo sobrevive a cerrar y abrir el programa. |
| Falla cerrada           | Si el CAPTCHA no se puede cargar, se niega el acceso en vez de saltarlo. |

## Alcance

Es un proyecto académico que demuestra conceptos de autenticación y mitigación de automatización. No reemplaza a un CAPTCHA de producción:

- Quien tenga acceso a la máquina puede borrar `lock_state.json` o adelantar el reloj del sistema.
- Si se cierra la ventana a mitad de una serie, los errores de esa serie no se guardan. Solo se guarda el bloqueo.
