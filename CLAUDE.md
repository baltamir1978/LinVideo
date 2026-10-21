# LinVideo — contexto del repositorio

Versión para Linux de **AppVideo** (macOS), escrita **desde cero en Python**, no portada. Lo común
a las apps de Linux (pila, `.deb`, dónde se prueba, la bandeja) está en el `CLAUDE.md` de la
carpeta de proyectos; aquí va lo propio de esta.

## Estado (21-oct-2026)

**Sin empezar.** Es la **piloto de Linux**: con ella se prueba todo de una vez (interfaz GTK 4,
GStreamer, procesos externos y el `.deb`) antes de LinBackup y LinRadio.

## La especificación es el original

`../AppVideo` (`github.com/baltamir1978/AppVideo`). Antes de escribir nada, leer su `README.md` y su
`CLAUDE.md`. Lo que se decidió allí **sigue valiendo aquí**:

- **Sin historial de descargas** (rechazado por Bruno). La cola pendiente sí se guarda, pero lo
  terminado nunca, y el archivo se borra al vaciarse.
- Al volver a abrir, **no se reanuda nada solo**: se enseña la lista con una casilla por descarga.
- **yt-dlp se actualiza solo**, una vez al día como mucho; si falla la red no cuenta como
  comprobado; se puede desactivar.
- **Una sola ventana**: un enlace nuevo va a la que ya está abierta.
- **Los errores de yt-dlp se traducen** a la causa real y a qué hacer.
- Los avisos legales, con una sola fuente de verdad.
- Las webs ya descartadas, y por qué, están en el `CLAUDE.md` del original: no volver a probarlas.

Qué hace: MP4 y MP3 a la máxima calidad, techo de resolución, recorte por tiempo, «Formatos…» con
la lista real de la web, GIF, buscador integrado (YouTube y unas 19 webs, por web, por categoría o
todas), vista previa sin descargar, cola con progreso, velocidad y registro, y **modo consola en el
mismo programa** (`--search`, `--formats`, `--preview`, `--clean-name`, `--update`…), que es la forma
de comprobar la lógica sin la interfaz.

## Cómo se hace en Linux

| En el Mac | Aquí |
|---|---|
| SwiftUI | GTK 4 + libadwaita (PyGObject) |
| yt-dlp, ffmpeg y ffprobe dentro del `.app` | **yt-dlp propio** en `~/.local/share/linvideo/bin/`, autoactualizable (el de apt va siempre atrasado); **ffmpeg y ffprobe de Debian** (`Depends: ffmpeg`) |
| `Process` leyendo la salida | `Gio.Subprocess` con `--newline` y `--progress-template` en JSON, para no interpretar texto |
| `URLSession` + parsers de HTML | `urllib` o `python3-requests`, y `html.parser` o `python3-bs4` |
| Vista previa con `AVPlayerView` | GStreamer `playbin3` en un `Gtk.Picture` (`gtk4paintablesink`, de `gstreamer1.0-gtk4`, si está en Debian 13; si no, libmpv con `python3-mpv`) |
| `~/Library/Application Support/AppVideo/pendientes.json` | `~/.local/share/linvideo/pendientes.json` |
| Carpeta de descargas | `xdg-user-dir DOWNLOAD` |
| «Mostrar en el Finder» | `org.freedesktop.FileManager1.ShowItems` por D-Bus |
| Enlaces `appvideo://` | `x-scheme-handler/linvideo` en el `.desktop` |

El ffmpeg de Debian es redistribuible. El del Mac no (lleva `--enable-nonfree`), y por eso allí
`Resources/bin/` está fuera de git.

**Lo que no hay en Linux:**

- **El menú Servicios.** Lo sustituye el enlace `linvideo://` con un bookmarklet en el navegador.
- **El aviso al copiar un enlace.** En Wayland una app sin foco no lee el portapapeles. Lo que sí se
  puede hacer: al recibir el foco, si el portapapeles tiene un enlace, ofrecerlo.

## Trampas que vienen del original

- **La consola y la interfaz deben llamar a la misma función de búsqueda federada.** En el original
  estaban duplicadas y se desincronizaron: la interfaz devolvía cero resultados en todas las webs
  menos YouTube y ninguna aparecía como fallida.
- **YouTube ya no da formatos con vídeo y audio juntos.** Para la vista previa va primero el HLS
  maestro (`manifest_url`), que arranca en 1–2 s; unir las pistas DASH tardaba más de dos minutos.
- **XVideos esconde a veces el enlace** (`/search-video/<blob>`). El identificador sigue en
  `data-eid` y con él se rehace la ruta.
- **Reddit**: `search.json` da 403 sin sesión, pero `/svc/shreddit/search/?type=media` sí responde;
  con `site:v.redd.it` en la consulta, todo lo que sale es vídeo. Pagina con cursor.
- **Un vídeo sin pista de audio no avanza si nadie pide la imagen** (pasaba con AVPlayer;
  comprobarlo con GStreamer).
- **Con la línea saturada, descargar en paralelo es más lento.** Por eso hay un presupuesto de
  conexiones en Ajustes.
- Las 10 fuentes que leen HTML se rompen cuando la web cambia: cada una aislada en su función y
  probada con una página guardada.

## Pruebas

`pytest` con páginas guardadas en `tests/fixtures/`. Traducir las del original
(`../AppVideo/Tests/AppVideoTests/`: parsers de búsqueda, argumentos de yt-dlp, limpieza de nombres,
errores, vista previa). La búsqueda federada necesita red y no la cubren: comprobarla por consola
con una categoría (`--search adult "algo"`).
