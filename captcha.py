"""CAPTCHA lógico visual basado en Piedra, Papel o Tijeras.

CAPTCHA elaborado por Kevin Villalobos Obando.

Se puede ejecutar directo (al validar abre el Área Protegida) o importar
desde otro programa y llamar a verificar_acceso() antes de construir su
ventana principal. Las imágenes van embebidas en base64 al final del
archivo, así que basta con entregar este .py.
"""

from __future__ import annotations

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
    # Sin Pillow las imágenes se cargan con el lector PNG que trae Tkinter
    Image = None
    ImageTk = None


TITULO_CAPTCHA = "CAPTCHA Lógico Visual"
ANCHO_VENTANA = 1000
ALTO_VENTANA = 700

# Segundos por ronda (el enunciado permite subirlo a 20)
TIEMPO_RONDA = 15
SEGUNDOS_DE_ALERTA = 5
ACIERTOS_PARA_VALIDAR = 2
ERRORES_PARA_BLOQUEAR = 2
# Al mejor de tres: la serie siempre se decide antes de pasar de 3 rondas
RONDAS_MAXIMAS = ACIERTOS_PARA_VALIDAR + ERRORES_PARA_BLOQUEAR - 1
DURACION_BLOQUEO = timedelta(seconds=50)
PAUSA_ENTRE_RONDAS_MS = 1000
# El bloqueo se refresca varias veces por segundo para que la cuenta no se salte números
REFRESCO_BLOQUEO_MS = 200

# Se ubica junto al .py y no en la carpeta desde donde se ejecuta,
# porque Code Runner y varios IDE arrancan en la raíz del proyecto
ARCHIVO_BLOQUEO = Path(__file__).resolve().parent / "data" / "lock_state.json"

TAMANO_IMAGEN_CENTRAL = (420, 270)
TAMANO_IMAGEN_BOTON = (210, 135)

FUENTE = "Arial"
COLOR_ACIERTO = "#2e7d32"
COLOR_ERROR = "#c62828"
FONDO_ACIERTO = "#c8e6c9"
FONDO_ERROR = "#ffcdd2"

# Relaciones del juego: la clave vence al valor (Piedra vence Tijeras, etc.)
VENCE_A = {"piedra": "tijeras", "papel": "piedra", "tijeras": "papel"}
# Invertido: para cada símbolo mostrado, cuál opción le gana
RESPUESTA_CORRECTA = {vencido: ganador for ganador, vencido in VENCE_A.items()}
NOMBRES = {"piedra": "Piedra", "papel": "Papel", "tijeras": "Tijeras"}

# Generador del sistema operativo: un bot no puede predecir la secuencia
AZAR = secrets.SystemRandom()


class GestorBloqueo:
    """Guarda y consulta el bloqueo temporal en data/lock_state.json."""

    def __init__(self, ruta: Path = ARCHIVO_BLOQUEO) -> None:
        self.ruta = ruta
        self.bloqueado_hasta: datetime | None = self._leer()

    # Devuelve cuánto falta para que termine el bloqueo, o None si no hay uno vigente
    def tiempo_restante(self) -> timedelta | None:
        if self.bloqueado_hasta is None:
            return None

        restante = self.bloqueado_hasta - datetime.now()

        if restante.total_seconds() <= 0:
            self.levantar()
            return None

        return restante

    # La sanción va a disco para que cerrar y abrir el programa no la evite
    def bloquear(self) -> None:
        self.bloqueado_hasta = (
            datetime.now() + DURACION_BLOQUEO
        ).replace(microsecond=0)

        estado = {"locked_until": self.bloqueado_hasta.isoformat()}

        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            self.ruta.write_text(json.dumps(estado, indent=4), encoding="utf-8")

        except OSError as error:
            # El bloqueo sigue activo en esta ejecución aunque no se pueda guardar
            print(f"No se pudo guardar el bloqueo en {self.ruta}: {error}", file=sys.stderr)

    # Se llama cuando el bloqueo ya venció
    def levantar(self) -> None:
        self.bloqueado_hasta = None

        try:
            self.ruta.unlink(missing_ok=True)

        except OSError as error:
            print(f"No se pudo borrar {self.ruta}: {error}", file=sys.stderr)

    # Un archivo dañado o editado a mano se ignora en vez de romper el programa
    def _leer(self) -> datetime | None:
        if not self.ruta.exists():
            return None

        try:
            estado = json.loads(self.ruta.read_text(encoding="utf-8"))
            return datetime.fromisoformat(estado["locked_until"])

        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            print(f"Archivo de bloqueo inválido ({self.ruta}): {error}", file=sys.stderr)
            return None


class PartidaCaptcha:
    """Marcador de una serie al mejor de tres, separado de la interfaz."""

    def __init__(self) -> None:
        self.ronda = 0
        self.aciertos = 0
        self.errores = 0
        self.simbolo_actual = ""

    # Sortea el símbolo que muestra la máquina en la siguiente ronda
    def nueva_ronda(self) -> str:
        self.ronda += 1
        self.simbolo_actual = AZAR.choice(list(VENCE_A))
        return self.simbolo_actual

    # opcion llega como None cuando se acabó el tiempo, y eso cuenta como error
    def registrar_respuesta(self, opcion: str | None) -> bool:
        acerto = opcion == RESPUESTA_CORRECTA[self.simbolo_actual]

        if acerto:
            self.aciertos += 1
        else:
            self.errores += 1

        return acerto

    def validada(self) -> bool:
        return self.aciertos >= ACIERTOS_PARA_VALIDAR

    def fallida(self) -> bool:
        return self.errores >= ERRORES_PARA_BLOQUEAR

    # El enunciado pide dejar los contadores en cero al terminar la serie
    def reiniciar(self) -> None:
        self.ronda = 0
        self.aciertos = 0
        self.errores = 0
        self.simbolo_actual = ""


class CaptchaApp:
    """Ventana del CAPTCHA. Solo marca validado = True si el usuario gana la serie."""

    def __init__(self, root: tk.Tk, anunciar_acceso: bool = True) -> None:
        self.root = root
        self.anunciar_acceso = anunciar_acceso
        self.validado = False
        self.partida = PartidaCaptcha()
        self.bloqueo = GestorBloqueo()
        self.esperando_respuesta = False
        self.segundos_restantes = 0
        # Nunca hay más de una tarea programada: el reloj, la pausa o el bloqueo
        self.tarea_pendiente: str | None = None
        self.boton_de_opcion: dict[str, tk.Button] = {}

        self.imagenes_centrales = cargar_imagenes(root, TAMANO_IMAGEN_CENTRAL)
        self.imagenes_boton = cargar_imagenes(root, TAMANO_IMAGEN_BOTON)

        self._configurar_ventana()
        self._construir_interfaz()
        self._iniciar()

    def _configurar_ventana(self) -> None:
        x = max(0, (self.root.winfo_screenwidth() - ANCHO_VENTANA) // 2)
        y = max(0, (self.root.winfo_screenheight() - ALTO_VENTANA) // 2 - 30)

        self.root.title(TITULO_CAPTCHA)
        self.root.geometry(f"{ANCHO_VENTANA}x{ALTO_VENTANA}+{x}+{y}")
        self.root.resizable(False, False)

        # Ícono transparente para quitar la pluma de Tkinter
        self.icono_vacio = tk.PhotoImage(master=self.root, width=1, height=1)
        self.root.iconphoto(True, self.icono_vacio)

        self.root.protocol("WM_DELETE_WINDOW", self._cerrar)

    # Encabezado e instrucciones quedan fijos; debajo se alterna juego o bloqueo
    def _construir_interfaz(self) -> None:
        tk.Label(
            self.root,
            text="CAPTCHA: Piedra, Papel o Tijeras",
            font=(FUENTE, 22, "bold")
        ).pack(pady=(20, 4))

        tk.Label(
            self.root,
            text=(
                f"Escoge la opción que le gana a la mía. Gana {ACIERTOS_PARA_VALIDAR} "
                f"de {RONDAS_MAXIMAS} rondas, con {TIEMPO_RONDA} segundos por ronda."
            ),
            font=(FUENTE, 11)
        ).pack()

        self.marco_juego = tk.Frame(self.root)
        self.marco_bloqueo = tk.Frame(self.root)

        self._construir_marcador()
        self._construir_tablero()
        self._construir_bloqueo()

    def _construir_marcador(self) -> None:
        marcador = tk.Frame(self.marco_juego)
        marcador.pack(pady=(12, 4))

        self.etiqueta_ronda = tk.Label(marcador, font=(FUENTE, 12, "bold"))
        self.etiqueta_aciertos = tk.Label(marcador, font=(FUENTE, 12, "bold"), fg=COLOR_ACIERTO)
        self.etiqueta_errores = tk.Label(marcador, font=(FUENTE, 12, "bold"), fg=COLOR_ERROR)
        self.etiqueta_tiempo = tk.Label(marcador, font=(FUENTE, 12, "bold"), width=12)

        for etiqueta in (
            self.etiqueta_ronda,
            self.etiqueta_aciertos,
            self.etiqueta_errores,
            self.etiqueta_tiempo
        ):
            etiqueta.pack(side="left", padx=25)

        self.color_texto = self.etiqueta_ronda.cget("fg")

    # La imagen vacía de 1 px hace que width/height se midan en píxeles y no en letras
    def _construir_tablero(self) -> None:
        ancho, alto = TAMANO_IMAGEN_CENTRAL
        ancho_boton, alto_boton = TAMANO_IMAGEN_BOTON

        tk.Label(self.marco_juego, text="MI OPCIÓN", font=(FUENTE, 10, "bold")).pack(pady=(6, 0))

        self.imagen_central = tk.Label(
            self.marco_juego,
            image=self.icono_vacio,
            width=ancho,
            height=alto
        )
        self.imagen_central.pack(pady=4)

        tk.Label(self.marco_juego, text="TU OPCIÓN", font=(FUENTE, 10, "bold")).pack(pady=(8, 0))

        fila = tk.Frame(self.marco_juego)
        fila.pack(pady=4)

        self.botones: list[tk.Button] = []

        for _ in VENCE_A:
            boton = tk.Button(
                fila,
                image=self.icono_vacio,
                width=ancho_boton + 10,
                height=alto_boton + 10,
                cursor="hand2",
                bd=2
            )
            boton.pack(side="left", padx=18)
            self.botones.append(boton)

        self.fondo_boton = self.botones[0].cget("bg")

        self.etiqueta_estado = tk.Label(self.marco_juego, font=(FUENTE, 13, "bold"))
        self.etiqueta_estado.pack(pady=(10, 0))

    def _construir_bloqueo(self) -> None:
        self.etiqueta_bloqueo = tk.Label(
            self.marco_bloqueo,
            font=(FUENTE, 20, "bold"),
            fg=COLOR_ERROR
        )
        self.etiqueta_bloqueo.pack(pady=(150, 20))

        tk.Label(
            self.marco_bloqueo,
            text=(
                f"Acumulaste {ERRORES_PARA_BLOQUEAR} errores. Podrás intentarlo de nuevo "
                "cuando la cuenta llegue a cero."
            ),
            font=(FUENTE, 11)
        ).pack()

    # Si quedó un bloqueo vigente de una ejecución anterior, no se deja jugar
    def _iniciar(self) -> None:
        if self.bloqueo.tiempo_restante() is None:
            self.marco_juego.pack(fill="both", expand=True)
            self._nueva_ronda()
        else:
            self._mostrar_bloqueo()

    # Cada ronda cambia el símbolo, el orden de los botones y reinicia el reloj
    def _nueva_ronda(self) -> None:
        simbolo = self.partida.nueva_ronda()
        self.imagen_central.config(image=self.imagenes_centrales[simbolo])

        opciones = list(VENCE_A)
        AZAR.shuffle(opciones)
        self.boton_de_opcion = dict(zip(opciones, self.botones))

        for opcion, boton in self.boton_de_opcion.items():
            boton.config(
                image=self.imagenes_boton[opcion],
                bg=self.fondo_boton,
                activebackground=self.fondo_boton,
                command=lambda elegida=opcion: self._responder(elegida)
            )

        self.etiqueta_estado.config(text="")
        self._actualizar_marcador()

        self.segundos_restantes = TIEMPO_RONDA
        self.esperando_respuesta = True
        self._avanzar_reloj()

    # Al llegar a cero la ronda se da por perdida
    def _avanzar_reloj(self) -> None:
        alerta = self.segundos_restantes <= SEGUNDOS_DE_ALERTA

        self.etiqueta_tiempo.config(
            text=f"Tiempo: {self.segundos_restantes} s",
            fg=COLOR_ERROR if alerta else self.color_texto
        )

        if self.segundos_restantes == 0:
            self._cerrar_ronda(None)
            return

        self.segundos_restantes -= 1
        self._programar(1000, self._avanzar_reloj)

    # Los clics que llegan durante la pausa de 1 s se ignoran para no contar doble
    def _responder(self, opcion: str) -> None:
        if self.esperando_respuesta:
            self._cerrar_ronda(opcion)

    # Termina la ronda (por clic o por tiempo) y pinta el resultado en verde o rojo
    def _cerrar_ronda(self, opcion: str | None) -> None:
        self.esperando_respuesta = False
        self._cancelar_pendiente()

        simbolo = NOMBRES[self.partida.simbolo_actual]
        acerto = self.partida.registrar_respuesta(opcion)

        if opcion is None:
            mensaje = "Se acabó el tiempo. La ronda cuenta como error."
        elif acerto:
            mensaje = f"¡Correcto! {NOMBRES[opcion]} le gana a {simbolo}."
        elif opcion == self.partida.simbolo_actual:
            mensaje = f"Incorrecto. {simbolo} contra {simbolo} es empate."
        else:
            mensaje = f"Incorrecto. {NOMBRES[opcion]} no le gana a {simbolo}."

        if opcion is not None:
            fondo = FONDO_ACIERTO if acerto else FONDO_ERROR
            self.boton_de_opcion[opcion].config(bg=fondo, activebackground=fondo)

        self.etiqueta_estado.config(text=mensaje, fg=COLOR_ACIERTO if acerto else COLOR_ERROR)
        self._actualizar_marcador()
        self._programar(PAUSA_ENTRE_RONDAS_MS, self._decidir_siguiente_paso)

    def _decidir_siguiente_paso(self) -> None:
        if self.partida.validada():
            self._conceder_acceso()
        elif self.partida.fallida():
            self._aplicar_bloqueo()
        else:
            self._nueva_ronda()

    def _actualizar_marcador(self) -> None:
        self.etiqueta_ronda.config(text=f"Ronda {self.partida.ronda} de {RONDAS_MAXIMAS}")
        self.etiqueta_aciertos.config(
            text=f"Aciertos: {self.partida.aciertos}/{ACIERTOS_PARA_VALIDAR}"
        )
        self.etiqueta_errores.config(
            text=f"Errores: {self.partida.errores}/{ERRORES_PARA_BLOQUEAR}"
        )

    # Orden pedido: primero la validación y después el acceso concedido
    def _conceder_acceso(self) -> None:
        self.etiqueta_estado.config(text="Validación completada correctamente", fg=COLOR_ACIERTO)

        messagebox.showinfo(
            TITULO_CAPTCHA,
            "Validación completada correctamente",
            parent=self.root
        )

        if self.anunciar_acceso:
            messagebox.showinfo("Área Protegida", "Acceso concedido", parent=self.root)

        self.partida.reiniciar()
        self.validado = True
        self._cerrar()

    # Sin ventana emergente, para que la cuenta regresiva se vea desde el primer segundo
    def _aplicar_bloqueo(self) -> None:
        self.bloqueo.bloquear()
        self.partida.reiniciar()
        self._mostrar_bloqueo()

    def _mostrar_bloqueo(self) -> None:
        self.marco_juego.pack_forget()
        self.marco_bloqueo.pack(fill="both", expand=True)
        self._refrescar_bloqueo()

    # Cuenta regresiva 50, 49, ... 0; al llegar a cero el CAPTCHA se habilita de nuevo
    def _refrescar_bloqueo(self) -> None:
        restante = self.bloqueo.tiempo_restante()
        segundos = 0 if restante is None else math.ceil(restante.total_seconds())
        unidad = "segundo" if segundos == 1 else "segundos"

        self.etiqueta_bloqueo.config(
            text=f"Acceso bloqueado.\nTiempo restante: {segundos} {unidad}"
        )

        if restante is None:
            # El cero queda a la vista un momento antes de volver al juego
            self._programar(PAUSA_ENTRE_RONDAS_MS, self._reanudar_juego)
        else:
            self._programar(REFRESCO_BLOQUEO_MS, self._refrescar_bloqueo)

    def _reanudar_juego(self) -> None:
        self.marco_bloqueo.pack_forget()
        self.marco_juego.pack(fill="both", expand=True)
        self._nueva_ronda()

    def _programar(self, milisegundos: int, accion: Callable[[], None]) -> None:
        self.tarea_pendiente = self.root.after(milisegundos, accion)

    def _cancelar_pendiente(self) -> None:
        if self.tarea_pendiente is not None:
            self.root.after_cancel(self.tarea_pendiente)
            self.tarea_pendiente = None

    # Cerrar la ventana sin validar equivale a negar el acceso
    def _cerrar(self) -> None:
        self._cancelar_pendiente()
        self.root.destroy()


class ProtectedApp:
    """Área Protegida de demostración: solo se crea después de superar el CAPTCHA."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Área Protegida")
        self.root.geometry("520x300")
        self.root.resizable(False, False)

        self.icono_vacio = tk.PhotoImage(master=self.root, width=1, height=1)
        self.root.iconphoto(True, self.icono_vacio)

        tk.Label(
            self.root,
            text="Acceso concedido",
            font=(FUENTE, 22, "bold"),
            fg=COLOR_ACIERTO
        ).pack(pady=(60, 10))

        tk.Label(
            self.root,
            text="El CAPTCHA lógico visual se completó correctamente.",
            font=(FUENTE, 11)
        ).pack()

        tk.Button(
            self.root,
            text="Salir",
            font=(FUENTE, 10),
            width=18,
            command=self.root.destroy
        ).pack(pady=40)

    def ejecutar(self) -> None:
        self.root.mainloop()


# Decodifica los PNG embebidos y los ajusta al tamaño pedido
def cargar_imagenes(
    master: tk.Misc,
    tamano: tuple[int, int]
) -> dict[str, ImageTk.PhotoImage | tk.PhotoImage]:
    imagenes = {}

    for simbolo, datos in IMAGENES_CAPTCHA.items():
        if Image is not None:
            # Se pasa a escala de grises porque Pillow no suaviza imágenes con paleta
            imagen = Image.open(BytesIO(base64.b64decode(datos))).convert("L")
            imagen.thumbnail(tamano, Image.LANCZOS)
            imagenes[simbolo] = ImageTk.PhotoImage(imagen, master=master)
        else:
            foto = tk.PhotoImage(master=master, data=datos)
            # Tkinter solo reduce por factores enteros, suficiente para los botones
            factor = math.ceil(max(foto.width() / tamano[0], foto.height() / tamano[1]))
            imagenes[simbolo] = foto.subsample(max(1, factor))

    return imagenes


# Muestra el CAPTCHA y devuelve True solo si el usuario lo superó.
# Ante cualquier fallo al prepararlo se niega el acceso en vez de saltarlo.
def verificar_acceso(anunciar_acceso: bool = True) -> bool:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"No se pudo abrir la ventana del CAPTCHA: {error}", file=sys.stderr)
        return False

    try:
        app = CaptchaApp(root, anunciar_acceso)

    except (tk.TclError, OSError, ValueError) as error:
        messagebox.showerror(
            TITULO_CAPTCHA,
            f"No fue posible cargar el CAPTCHA.\n\n{error}",
            parent=root
        )
        root.destroy()
        return False

    root.mainloop()
    return app.validado


# El Área Protegida solo se construye si el CAPTCHA se supera
def main() -> None:
    if verificar_acceso(anunciar_acceso=False):
        ProtectedApp().ejecutar()


# Imágenes del CAPTCHA en PNG (escala de grises, 4 tonos) codificadas en base64.
# Van dentro del código para que el programa funcione entregando solo el .py.
IMAGENES_CAPTCHA: dict[str, str] = {
    "piedra": (
        "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"
    ),
    "papel": (
        "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"
        "D2s5h/RDJfrhAAAAAElFTkSuQmCC"
    ),
    "tijeras": (
        "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"
    ),
}


if __name__ == "__main__":
    main()
