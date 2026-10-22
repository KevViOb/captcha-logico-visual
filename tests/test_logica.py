"""Pruebas de las reglas, el marcador y el bloqueo. No abren ninguna ventana."""

import base64
import json
from datetime import datetime, timedelta

import pytest

import captcha
from captcha import (
    IMAGENES_CAPTCHA,
    RESPUESTA_CORRECTA,
    RONDAS_MAXIMAS,
    VENCE_A,
    GestorBloqueo,
    PartidaCaptcha,
)

FIRMA_PNG = b"\x89PNG\r\n\x1a\n"


class RelojFalso(datetime):
    """datetime con la hora fija, para no depender del reloj real ni usar sleep."""

    actual = datetime(2026, 10, 22, 12, 0, 0)

    @classmethod
    def now(cls, tz=None):
        return cls.actual


@pytest.fixture
def reloj(monkeypatch):
    RelojFalso.actual = datetime(2026, 10, 22, 12, 0, 0)
    monkeypatch.setattr(captcha, "datetime", RelojFalso)
    return RelojFalso


@pytest.fixture
def ruta(tmp_path):
    return tmp_path / "data" / "lock_state.json"


def escribir_bloqueo(ruta, valor):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"locked_until": valor}), encoding="utf-8")


def jugar_ronda(partida, gana):
    partida.nueva_ronda()
    opcion = RESPUESTA_CORRECTA[partida.simbolo_actual] if gana else partida.simbolo_actual
    return partida.registrar_respuesta(opcion)


@pytest.mark.parametrize(
    "mostrado, ganadora",
    [("piedra", "papel"), ("papel", "tijeras"), ("tijeras", "piedra")],
)
def test_respuesta_correcta_es_la_opcion_que_vence_al_simbolo(mostrado, ganadora):
    assert RESPUESTA_CORRECTA[mostrado] == ganadora
    assert VENCE_A[ganadora] == mostrado


def test_rondas_maximas_corresponden_al_mejor_de_tres():
    assert RONDAS_MAXIMAS == 3


def test_registrar_respuesta_con_opcion_ganadora_suma_acierto():
    partida = PartidaCaptcha()

    acerto = jugar_ronda(partida, gana=True)

    assert acerto
    assert (partida.aciertos, partida.errores) == (1, 0)


def test_registrar_respuesta_con_empate_suma_error():
    partida = PartidaCaptcha()

    acerto = jugar_ronda(partida, gana=False)

    assert not acerto
    assert (partida.aciertos, partida.errores) == (0, 1)


def test_registrar_respuesta_sin_opcion_por_tiempo_agotado_suma_error():
    partida = PartidaCaptcha()
    partida.nueva_ronda()

    acerto = partida.registrar_respuesta(None)

    assert not acerto
    assert partida.errores == 1


def test_partida_con_dos_aciertos_queda_validada():
    partida = PartidaCaptcha()

    jugar_ronda(partida, gana=True)
    jugar_ronda(partida, gana=True)

    assert partida.validada()
    assert not partida.fallida()


def test_partida_con_dos_errores_queda_fallida():
    partida = PartidaCaptcha()

    jugar_ronda(partida, gana=False)
    jugar_ronda(partida, gana=False)

    assert partida.fallida()
    assert not partida.validada()


def test_partida_empatada_uno_a_uno_se_decide_en_la_tercera_ronda():
    partida = PartidaCaptcha()
    jugar_ronda(partida, gana=True)
    jugar_ronda(partida, gana=False)
    assert not partida.validada() and not partida.fallida()

    jugar_ronda(partida, gana=True)

    assert partida.validada()
    assert partida.ronda == 3


def test_reiniciar_deja_los_contadores_en_cero():
    partida = PartidaCaptcha()
    jugar_ronda(partida, gana=True)
    jugar_ronda(partida, gana=False)

    partida.reiniciar()

    assert (partida.ronda, partida.aciertos, partida.errores) == (0, 0, 0)


def test_nueva_ronda_sortea_los_tres_simbolos():
    vistos = {PartidaCaptcha().nueva_ronda() for _ in range(300)}

    assert vistos == set(VENCE_A)


def test_sin_archivo_no_hay_bloqueo(ruta, reloj):
    assert GestorBloqueo(ruta).tiempo_restante() is None


def test_bloquear_guarda_el_formato_del_enunciado(ruta, reloj):
    gestor = GestorBloqueo(ruta)

    gestor.bloquear()

    assert json.loads(ruta.read_text(encoding="utf-8")) == {"locked_until": "2026-10-22T12:00:50"}
    assert gestor.tiempo_restante() == timedelta(seconds=50)


def test_bloqueo_vigente_se_mantiene_al_reabrir(ruta, reloj):
    GestorBloqueo(ruta).bloquear()

    reloj.actual += timedelta(seconds=20)

    assert GestorBloqueo(ruta).tiempo_restante() == timedelta(seconds=30)


def test_bloqueo_vencido_se_levanta_y_borra_el_archivo(ruta, reloj):
    GestorBloqueo(ruta).bloquear()

    reloj.actual += timedelta(seconds=51)

    assert GestorBloqueo(ruta).tiempo_restante() is None
    assert not ruta.exists()


@pytest.mark.parametrize(
    "contenido",
    ["{no es json", '{"otra": 1}', "[1, 2]", '{"locked_until": 5}', '{"locked_until": "ayer"}'],
)
def test_archivo_danado_se_ignora(ruta, reloj, contenido):
    ruta.parent.mkdir(parents=True)
    ruta.write_text(contenido, encoding="utf-8")

    assert GestorBloqueo(ruta).tiempo_restante() is None


def test_bloqueo_mas_largo_que_la_duracion_se_recorta(ruta, reloj):
    escribir_bloqueo(ruta, "2026-10-22T12:30:00")

    restante = GestorBloqueo(ruta).tiempo_restante()

    assert restante == timedelta(seconds=50)
    assert json.loads(ruta.read_text(encoding="utf-8")) == {"locked_until": "2026-10-22T12:00:50"}


def test_bloqueo_recortado_no_se_reinicia_al_reabrir(ruta, reloj):
    escribir_bloqueo(ruta, "2026-10-22T12:30:00")
    GestorBloqueo(ruta)

    reloj.actual += timedelta(seconds=10)

    assert GestorBloqueo(ruta).tiempo_restante() == timedelta(seconds=40)


def test_fecha_con_zona_horaria_se_compara_en_hora_local(ruta, reloj):
    con_zona = (reloj.actual.astimezone() + timedelta(seconds=20)).isoformat()
    escribir_bloqueo(ruta, con_zona)

    assert GestorBloqueo(ruta).tiempo_restante() == timedelta(seconds=20)


@pytest.mark.parametrize("simbolo", sorted(VENCE_A))
def test_imagen_embebida_es_un_png_valido(simbolo):
    datos = base64.b64decode(IMAGENES_CAPTCHA[simbolo], validate=True)

    assert datos.startswith(FIRMA_PNG)
