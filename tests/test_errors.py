"""Los errores de yt-dlp llegan en inglés y con detalles internos; lo que ve el usuario
tiene que decir qué ha pasado y qué hacer."""

from linvideo.errors import clean, explain


def test_sin_pista_de_audio() -> None:
    message = explain(["ERROR: Postprocessing: WARNING: unable to obtain file audio codec "
                       "with ffprobe"], 1)
    assert "no tiene pista de audio" in message
    assert "vídeo" in message.lower() or "gif" in message.lower()


def test_video_retirado() -> None:
    message = explain(["ERROR: [youtube] BROWqjuTM0g: Video unavailable. It was removed "
                       "following a copyright removal request"], 1)
    assert "ya no está disponible" in message


def test_video_no_disponible() -> None:
    # Así lo escribe YouTube con un identificador que no existe (21-oct-2026).
    message = explain(["ERROR: [youtube] xxxxxxxxxxx: This video is unavailable"], 1)
    assert "ya no está disponible" in message


def test_verificacion_de_edad() -> None:
    message = explain(["ERROR: [youtube] abc: Sign in to confirm your age. This video may be "
                       "inappropriate for some users."], 1)
    assert "Ajustes" in message and "edad" in message.lower()


def test_403() -> None:
    message = explain(["ERROR: unable to download video data: HTTP Error 403: Forbidden"], 1)
    assert "403" in message and "yt-dlp" in message


def test_429() -> None:
    message = explain(["ERROR: HTTP Error 429: Too Many Requests"], 1)
    assert "simultáneas" in message or "Espera" in message


def test_sin_espacio() -> None:
    assert "espacio" in explain(["ERROR: unable to write data: No space left on device"], 1)


def test_ffmpeg_que_falta_se_instala_con_apt() -> None:
    assert "apt install ffmpeg" in explain(["ERROR: ffmpeg not found."], 1)


def test_error_desconocido() -> None:
    message = explain(["ERROR: [sitio] 123: algo muy raro ha pasado"], 1)
    assert not message.startswith("ERROR")
    assert "algo muy raro" in message


def test_sin_lineas() -> None:
    assert "2" in explain([], 2)


def test_limpia_el_texto() -> None:
    assert clean("ERROR: algo") == "algo"
    assert clean("WARNING: otra cosa") == "otra cosa"
    assert clean("[youtube] abc123: mensaje") == "mensaje"
    assert clean("fallo (caused by TransportError())") == "fallo"
