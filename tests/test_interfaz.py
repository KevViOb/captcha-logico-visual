"""Pruebas de la ventana del CAPTCHA.

La ventana se crea oculta, así que no aparece nada en pantalla. Si no hay
pantalla disponible (por ejemplo en un servidor sin entorno gráfico), las
pruebas se omiten solas.
"""

import time
import tkinter as tk

import pytest

import captcha
from captcha import RESPUESTA_CORRECTA, CaptchaApp, GestorBloqueo


@pytest.fixture
def ruta(tmp_path):
    return tmp_path / "data" / "lock_state.json"


@pytest.fixture
def mensajes(monkeypatch):
    registro = []
    monkeypatch.setattr(captcha.messagebox, "showinfo", lambda t, m, **k: registro.append(m))
    return registro


@pytest.fixture
def root(monkeypatch, ruta, mensajes):
    try:
        ventana = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"No hay pantalla disponible para Tkinter: {error}")

    ventana.withdraw()
    # Pausa corta entre rondas y bloqueo en una carpeta temporal, nunca en data/ real
    monkeypatch.setattr(captcha, "PAUSA_ENTRE_RONDAS_MS", 10)
    monkeypatch.setattr(captcha, "GestorBloqueo", lambda: GestorBloqueo(ruta))

    yield ventana

    try:
        ventana.destroy()
    except tk.TclError:
        pass


def esperar(root, condicion, limite=3.0):
    fin = time.monotonic() + limite
    while not condicion() and time.monotonic() < fin:
        root.update()
        time.sleep(0.01)
    return condicion()


def responder(app, gana):
    simbolo = app.partida.simbolo_actual
    opcion = RESPUESTA_CORRECTA[simbolo] if gana else simbolo
    app.boton_de_opcion[opcion].invoke()


def test_ganar_dos_rondas_valida_y_anuncia_en_orden(root, mensajes):
    app = CaptchaApp(root)

    for _ in range(2):
        assert esperar(root, lambda: app.esperando_respuesta)
        responder(app, gana=True)

    assert esperar(root, lambda: app.validado)
    assert mensajes == ["Validación completada correctamente", "Acceso concedido"]


def test_perder_dos_rondas_bloquea_y_guarda_el_archivo(root, ruta):
    app = CaptchaApp(root)

    for _ in range(2):
        assert esperar(root, lambda: app.esperando_respuesta)
        responder(app, gana=False)

    assert esperar(root, lambda: app.marco_bloqueo.winfo_manager() == "pack")
    assert ruta.exists()
    assert "segundos" in app.etiqueta_bloqueo.cget("text")
    assert not app.validado


def test_doble_clic_cuenta_una_sola_vez(root):
    app = CaptchaApp(root)
    boton = app.boton_de_opcion[RESPUESTA_CORRECTA[app.partida.simbolo_actual]]

    boton.invoke()
    boton.invoke()

    assert (app.partida.aciertos, app.partida.errores) == (1, 0)


def test_tiempo_agotado_cuenta_como_error(root, monkeypatch):
    monkeypatch.setattr(captcha, "TIEMPO_RONDA", 1)
    app = CaptchaApp(root)

    assert esperar(root, lambda: app.partida.errores == 1)
    assert "tiempo" in app.etiqueta_estado.cget("text")


def test_bloqueo_previo_impide_jugar_al_abrir(root, ruta):
    GestorBloqueo(ruta).bloquear()

    app = CaptchaApp(root)

    assert app.marco_bloqueo.winfo_manager() == "pack"
    assert app.marco_juego.winfo_manager() == ""


def test_cerrar_la_ventana_niega_el_acceso(root):
    app = CaptchaApp(root)

    app._cerrar()

    assert not app.validado
