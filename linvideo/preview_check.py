"""`--preview`: comprobar con GStreamer que el flujo elegido arranca de verdad.

«Listo» no basta: hay flujos que abren y luego no entregan ni un segmento, así que se
reproduce en silencio hasta que avanza el reloj.

Sin probar todavía (21-oct-2026): en el Mac no hay GStreamer. Necesita en Debian
`python3-gst-1.0`, `gstreamer1.0-plugins-good`, `-bad` y `gstreamer1.0-libav`.
"""

import time

from .preview import PreviewStream


class Unavailable(Exception):
    """No hay GStreamer con el que comprobarlo."""


def check(stream: PreviewStream, seconds: float = 20) -> tuple[float, str]:
    """Devuelve (segundos hasta arrancar, tamaño de la imagen o «sin imagen»).

    Lanza `Unavailable` si no hay GStreamer y `RuntimeError` si no arranca.
    """
    try:
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
    except (ImportError, ValueError) as error:
        raise Unavailable(str(error)) from error

    Gst.init(None)
    player = Gst.ElementFactory.make("playbin3", None) or Gst.ElementFactory.make("playbin", None)
    if player is None:
        raise Unavailable("GStreamer no tiene playbin")
    # Sin altavoces: las pruebas no deben sonar. La imagen sí se pide (fakesink sincronizado):
    # un vídeo sin pista de audio no avanza si nadie consume la imagen.
    player.set_property("audio-sink", Gst.ElementFactory.make("fakesink", None))
    video_sink = Gst.ElementFactory.make("fakesink", None)
    video_sink.set_property("sync", True)
    player.set_property("video-sink", video_sink)
    player.set_property("uri", stream.url)

    def on_source(_bin: object, source: object) -> None:
        # Las cabeceras que pide la web van en el elemento que descarga (souphttpsrc).
        props = [p.name for p in source.list_properties()]  # type: ignore[attr-defined]
        if "user-agent" in props and "User-Agent" in stream.headers:
            source.set_property("user-agent", stream.headers["User-Agent"])  # type: ignore[attr-defined]
        if "extra-headers" in props:
            extra = Gst.Structure.new_empty("extra-headers")
            for key, value in stream.headers.items():
                if key.lower() != "user-agent":
                    extra.set_value(key, value)
            source.set_property("extra-headers", extra)  # type: ignore[attr-defined]

    player.connect("source-setup", on_source)
    bus = player.get_bus()
    start = time.monotonic()
    player.set_state(Gst.State.PLAYING)
    try:
        while time.monotonic() - start < seconds:
            message = bus.timed_pop_filtered(250 * Gst.MSECOND, Gst.MessageType.ERROR)
            if message is not None:
                gerror, _debug = message.parse_error()
                raise RuntimeError(f"GStreamer: {gerror.message}")
            ok, position = player.query_position(Gst.Format.TIME)
            if ok and position > Gst.SECOND:
                caps = None
                pad = video_sink.get_static_pad("sink")
                if pad is not None:
                    caps = pad.get_current_caps()
                picture = "sin imagen"
                if caps is not None and caps.get_size() > 0:
                    structure = caps.get_structure(0)
                    ok_w, width = structure.get_int("width")
                    ok_h, height = structure.get_int("height")
                    if ok_w and ok_h:
                        picture = f"{width}×{height}"
                return time.monotonic() - start - 1, picture
        raise RuntimeError(f"GStreamer no arrancó en {int(seconds)} s")
    finally:
        player.set_state(Gst.State.NULL)
