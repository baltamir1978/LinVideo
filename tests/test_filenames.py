"""Casos tomados de descargas reales, más los bordes que rompieron la primera versión."""

from linvideo.filenames import clean, replace_problematic_characters, split_extension, truncate
from linvideo.models import FilenameCleanup

BASIC = FilenameCleanup.BASIC
STRICT = FilenameCleanup.STRICT


def test_quita_el_identificador() -> None:
    assert clean("Me at the zoo [jNQXAC9IVRw].mp4", BASIC) == "Me at the zoo.mp4"


def test_quita_etiquetas_de_relleno() -> None:
    assert clean("Luis Fonsi - Despacito ft. Daddy Yankee (Official Video) [kJQP7kiw5Fk].mp4",
                 BASIC) == "Luis Fonsi - Despacito ft. Daddy Yankee.mp4"


def test_quita_ruido() -> None:
    assert "🥵" not in clean("Juro a Dios 🥵😬 esta boca [68e2bb75].mp4", BASIC)
    no_hashtags = clean("Playa #amateur #real [1atcfzcf].mp4", BASIC)
    assert "#" not in no_hashtags and no_hashtags.startswith("Playa")
    assert "xvideos" not in clean("Algo bonito | XVIDEOS.COM [abc123].mp4", BASIC).lower()


def test_quita_etiquetas_finales() -> None:
    assert clean("Documental sobre jazz 4K FULL HD [x8mlmc3].mp4", BASIC) == \
        "Documental sobre jazz.mp4"


def test_respeta_las_barras() -> None:
    # Rompía la primera versión: todo lo anterior a la barra se tomaba por carpeta.
    cleaned = clean("Best of lofi 2021 [beats to relax/study to] [n61ULEU7CO0].webm", BASIC)
    assert cleaned.startswith("Best of lofi 2021")
    assert cleaned.endswith(".webm")
    assert "/" not in cleaned


def test_modo_estricto() -> None:
    assert clean("Concierto (en directo) [abc12345].mp4", STRICT) == "Concierto.mp4"
    assert clean("ESTE TÍTULO ESTÁ TODO EN MAYÚSCULAS [abc12345].mp4", STRICT) == \
        "Este Título Está Todo En Mayúsculas.mp4"


def test_mayusculas_con_apostrofo() -> None:
    # `str.title()` dejaría «Don'T»; aquí se va palabra a palabra.
    assert clean("DON'T STOP ME NOW QUEEN [abc12345].mp4", STRICT) == "Don't Stop Me Now Queen.mp4"


def test_sin_limpieza() -> None:
    original = "Me at the zoo [jNQXAC9IVRw].mp4"
    assert clean(original, FilenameCleanup.NONE) == original


def test_conserva_el_identificador() -> None:
    assert "[jNQXAC9IVRw]" in clean("Me at the zoo [jNQXAC9IVRw].mp4", BASIC, keep_identifier=True)


def test_nunca_vacio() -> None:
    assert clean("#️⃣ [abc12345].mp4", STRICT)


def test_separa_extension() -> None:
    assert split_extension("vídeo.mp4") == ("vídeo", "mp4")
    # Un punto en mitad del título no es una extensión.
    assert split_extension("Cap. 3 del documental")[1] == ""
    assert split_extension("sin extension")[1] == ""


def test_recorta() -> None:
    cut = truncate("palabra " * 40, 50)
    assert len(cut) <= 50
    assert not cut.endswith("pal")


def test_caracteres_problematicos() -> None:
    cleaned = replace_problematic_characters("a/b:c|d")
    assert "/" not in cleaned and "|" not in cleaned
