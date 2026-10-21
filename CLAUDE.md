# LinVideo — contexto del repositorio

Versión para Linux de **AppVideo** (macOS), escrita **desde cero en Python**, no portada. Lo común
a las apps de Linux (pila, `.deb`, dónde se prueba, la bandeja) está en el `CLAUDE.md` de la
carpeta de proyectos; aquí va lo propio de esta.

## Estado (21-oct-2026)

Es la **piloto de Linux**: con ella se prueba todo de una vez (interfaz GTK 4, GStreamer,
procesos externos y el `.deb`) antes de LinBackup y LinRadio.

**Hecho y probado en el Mac:** el núcleo y el modo consola, el `.deb` y 100 pruebas.
- Descargas: vídeo, MP3 con portada, GIF, recorte y cancelación con Ctrl-C (código 130, sin
  procesos colgados, el `.part` se queda para reanudar).
- Búsqueda en las 19 webs: contestan todas igual que en AppVideo.
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

## Lo que se encontró al traducir (arreglado también en AppVideo, commit 200eef1)

- **«ffmpeg not found» se explicaba como un 404**: la regla genérica «not found» iba antes que la
  de ffmpeg.
- **«This video is unavailable»**, como lo escribe YouTube con un identificador que no existe, no
  casaba con «video unavailable» y salía en inglés.
- **Una búsqueda sin resultados se presentaba como si la web hubiera cambiado** («no devolvió
  resultados legibles»). Se creyó primero que TNAFlix y YouJizz estaban rotas, y no: con «jazz
  piano» no tienen nada, y con «amateur» devuelven 24. Ahora `says_no_results` reconoce el aviso
  de cada web: XVideos y XNXX en español; TNAFlix, YouJizz y ThisVid en inglés; Pornhub y YouPorn
  responden 404, y Pornhub redirige a `es.pornhub.com` por el idioma. Con el aviso, la lista va
  vacía aunque se haya leído algo, porque ThisVid pone vídeos en tendencia debajo y se colaban
  como resultados. PornTrex no da ninguna señal y sigue contando como fallo.
- **Ojo al diagnosticar una web «rota»**: probar antes con una búsqueda corriente. Eporner, por
  ejemplo, devuelve una lista vacía con «jazz piano» y 24 con «amateur».
