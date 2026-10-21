# LinVideo

Descarga vídeo en MP4 y audio en MP3 con la máxima calidad desde YouTube y más de mil webs,
con buscador integrado en una veintena de ellas, recorte por tiempo, GIF y errores explicados
en claro. Funciona sobre [yt-dlp](https://github.com/yt-dlp/yt-dlp) y FFmpeg.

Versión para Linux de [AppVideo](https://github.com/baltamir1978/AppVideo), la app de macOS. No es
un port: se escribe desde cero en Python, con la app original como especificación.

**Estado (21-oct-2026): funciona el modo consola.** La ventana (GTK 4 + libadwaita) todavía no
existe.

## Instalar en Debian

```sh
Tools/build-deb.sh                          # genera build/linvideo_<versión>_all.deb
sudo apt install ./build/linvideo_*_all.deb
linvideo --update                           # baja su propia copia de yt-dlp
```

El paquete sólo depende de `python3` y `ffmpeg`. yt-dlp no se toma de apt, que va siempre
atrasado: LinVideo mantiene su propia copia en `~/.local/share/linvideo/bin` y la actualiza sin
permisos de root.

## Uso

```sh
linvideo <url>                         # vídeo en la máxima calidad, a la carpeta de descargas
linvideo <url> --mp3                   # audio en MP3, con portada y etiquetas
linvideo <url> --max 720 --from 1:30 --to 2:00
linvideo <url> --gif --to 0:05 --width 320
linvideo --search youtube "algo"       # o reddit, soundcloud…, una categoría o «all»
linvideo --formats <url>               # los formatos reales del enlace
linvideo --help                        # todo lo demás
```

Ctrl-C cancela; lo descargado se conserva y la siguiente vez se reanuda.

## Dónde guarda las cosas

| Qué | Dónde |
|---|---|
| Ajustes | `~/.config/linvideo/ajustes.json` |
| Descargas a medias (no es un historial) | `~/.local/share/linvideo/pendientes.json` |
| yt-dlp actualizable | `~/.local/share/linvideo/bin/yt-dlp` |
| Última comprobación de versión | `~/.local/state/linvideo/actualizacion.json` |

## Desarrollo

```sh
python3 -m venv .venv && .venv/bin/pip install pytest mypy
.venv/bin/pytest          # 100 pruebas
.venv/bin/mypy            # tipos estrictos, para Python 3.13
.venv/bin/python -m linvideo --help
```

## Aviso legal

LinVideo es una interfaz para yt-dlp y FFmpeg pensada para uso personal. Quien la usa es
responsable de lo que descarga. El texto completo: `linvideo --legal`.
