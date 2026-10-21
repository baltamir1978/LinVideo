# LinVideo — contexto del repositorio

Versión para Linux de **AppVideo** (macOS), escrita **desde cero en Python**, no portada. Lo común
a las apps de Linux (pila, `.deb`, dónde se prueba, la bandeja) está en el `CLAUDE.md` de la
carpeta de proyectos; aquí va lo propio de esta.

## Estado (21-oct-2026)

Es la **piloto de Linux**: con ella se prueba todo de una vez (interfaz GTK 4, GStreamer,
procesos externos y el `.deb`) antes de LinBackup y LinRadio.

**Hecho y probado en el Mac:** el núcleo y el modo consola, el `.deb` y 90 pruebas.
- Descargas: vídeo, MP3 con portada, GIF, recorte y cancelación con Ctrl-C (código 130, sin
  procesos colgados, el `.part` se queda para reanudar).
- Búsqueda en las 19 webs: contestan 16, las mismas que en AppVideo (ver abajo).
- `--formats`, `--update`, `--clean-name`, `--prefs`, `--tools`, `--pending`, `--legal`.

**Escrito pero sin probar:** la comprobación de la vista previa con GStreamer
(`preview_check.py`), porque en el Mac no hay GStreamer.

**Falta:**
- **La ventana** (GTK 4 + libadwaita): pestañas Descargar y Buscar, cola con descargas
  simultáneas, Ajustes, aviso legal al primer arranque, recuperar la cola pendiente.
- **Lo que llega con la ventana**: el `.desktop` (con `x-scheme-handler/linvideo`), el icono y
  las dependencias de GTK y GStreamer en el `control`.
- **Probarlo en Debian de verdad.**

## Cómo se prueba

```sh
.venv/bin/pytest && .venv/bin/mypy          # el entorno virtual está en .gitignore
Tools/build-deb.sh --check                  # monta el .deb, mira dentro y lo arranca
```

Para usar el modo consola sin tocar la carpeta personal, las carpetas XDG pueden apuntar a otro
sitio: `XDG_CONFIG_HOME=… XDG_DATA_HOME=… XDG_STATE_HOME=… .venv/bin/python -m linvideo …`.
Así se probó todo en el Mac.

**El Mac sólo tiene Python 3.14** (Homebrew) y Debian 13 lleva el 3.13: no usar nada nuevo de la
3.14. `mypy` comprueba contra la 3.13 (`pyproject.toml`), pero eso no detecta todo.

## Decisiones tomadas aquí

- **Todo con la biblioteca estándar** (`urllib`, `html`, `json`, `subprocess`): el paquete sólo
  depende de `python3` y `ffmpeg`.
- **yt-dlp es el «zipapp»** (`releases/latest/download/yt-dlp`), un script de Python que sirve en
  cualquier arquitectura, igual que el `.deb` (`Architecture: all`). Se ejecuta con el
  intérprete que corre LinVideo (`tools.command`), no con el `python3` del PATH: en el Mac ese es
  el 3.9, demasiado viejo para yt-dlp.
- **El User-Agent de las búsquedas es el de Safari en Mac, el mismo de AppVideo**, aunque esto sea
  Linux. Con el de Firefox en Linux, Pornhub sirve otra maquetación y no se lee nada (comprobado
  el 21-oct-2026). Los lectores se escribieron para la página que reciben con ese.
- **La vista previa admite más formatos que en el Mac**: GStreamer abre WebM, VP9, AV1 y Opus. Se
  siguen descartando los segmentos DASH sueltos y las miniaturas `mhtml`.
- **Las opciones extra de yt-dlp respetan las comillas** (`shlex`); en AppVideo se partían por
  espacios.
- **Las cookies del navegador**: Firefox, Chromium, Chrome, Brave, Edge y Vivaldi. Safari no
  existe en Linux.

## Lo que se encontró al traducir, y que también afecta a AppVideo

- **«ffmpeg not found» se explicaba como un 404**: la regla genérica «not found» iba antes que la
  de ffmpeg. Aquí ya va detrás.
- **«This video is unavailable»**, como lo escribe YouTube con un identificador que no existe, no
  casaba con «video unavailable» y salía en inglés. Aquí ya se reconoce.
- **TNAFlix y YouJizz no devuelven nada** en ninguna de las dos apps (21-oct-2026): han cambiado la
  página. Eporner devuelve una lista vacía con «jazz piano» en las dos, así que eso depende de la
  búsqueda y no es un fallo.

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
