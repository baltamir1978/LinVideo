#!/usr/bin/env bash
# Monta el paquete .deb de LinVideo en build/.
#
#   Tools/build-deb.sh            → build/linvideo_<versión>+<AAMMDDHHMM>_all.deb
#   Tools/build-deb.sh --check    → además, comprueba el paquete por dentro
#
# Funciona igual en Debian que en el Mac (dpkg-deb de Homebrew: brew install dpkg).
# El paquete es `Architecture: all`: sólo lleva Python, no hay nada que compilar.
# Se instala en Debian con: sudo apt install ./build/linvideo_…_all.deb
set -euo pipefail

cd "$(dirname "$0")/.."

command -v dpkg-deb >/dev/null || { echo "✗ Falta dpkg-deb (Debian: viene de serie; Mac: brew install dpkg)"; exit 1; }

VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' linvideo/__init__.py)
[ -n "$VERSION" ] || { echo "✗ No encuentro __version__ en linvideo/__init__.py"; exit 1; }
# Fecha y hora como número de compilación, igual que en TestFlight: siempre crece.
BUILD=$(date +%y%m%d%H%M)
FULL="$VERSION+$BUILD"
NAME="linvideo_${FULL}_all"
ROOT="build/$NAME"

rm -rf "$ROOT" "build/$NAME.deb"
mkdir -p "$ROOT/DEBIAN" "$ROOT/usr/bin" "$ROOT/usr/lib/linvideo" "$ROOT/usr/share/doc/linvideo"

# El código, sin cachés ni basura del Mac.
mkdir -p "$ROOT/usr/lib/linvideo/linvideo"
for f in linvideo/*.py; do
    install -m 644 "$f" "$ROOT/usr/lib/linvideo/linvideo/"
done

# El lanzador usa el Python del sistema (el de Debian 13 es el 3.13).
cat > "$ROOT/usr/bin/linvideo" <<'EOF'
#!/usr/bin/python3
import sys
sys.path.insert(0, "/usr/lib/linvideo")
from linvideo.__main__ import main
sys.exit(main())
EOF
chmod 755 "$ROOT/usr/bin/linvideo"

cat > "$ROOT/usr/share/doc/linvideo/copyright" <<'EOF'
LinVideo
Copyright 2026 Bruno Altamirano
Código: https://github.com/baltamir1978/LinVideo

LinVideo no lleva yt-dlp ni FFmpeg dentro. Usa el FFmpeg del sistema y descarga su propia
copia de yt-dlp (dominio público, The Unlicense) en ~/.local/share/linvideo/bin.
EOF
chmod 644 "$ROOT/usr/share/doc/linvideo/copyright"

# Los .pyc se generan al instalar y se borran al desinstalar: así dpkg no tiene que
# conocerlos y no quedan restos.
cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    python3 -m compileall -q /usr/lib/linvideo >/dev/null 2>&1 || true
fi
EOF
cat > "$ROOT/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
find /usr/lib/linvideo -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
EOF
chmod 755 "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/prerm"

SIZE=$(du -sk "$ROOT/usr" | cut -f1)
cat > "$ROOT/DEBIAN/control" <<EOF
Package: linvideo
Version: $FULL
Section: video
Priority: optional
Architecture: all
Depends: python3 (>= 3.11), ffmpeg
Suggests: yt-dlp
Installed-Size: $SIZE
Maintainer: Bruno Altamirano <baltamir1978@users.noreply.github.com>
Homepage: https://github.com/baltamir1978/LinVideo
Description: descargas de vídeo y audio con yt-dlp, con buscador
 Descarga vídeo en MP4 y audio en MP3 con la máxima calidad desde YouTube y
 más de mil webs, con buscador integrado en una veintena de ellas, recorte por
 tiempo, GIF y errores explicados. Por ahora sólo en modo consola: linvideo --help
 .
 Mantiene su propia copia de yt-dlp, que se actualiza sola; la del paquete de
 Debian va siempre atrasada.
EOF

# Directorios a 755 y propietario root en el paquete, se construya donde se construya.
find "$ROOT" -type d -exec chmod 755 {} +
COPYFILE_DISABLE=1 dpkg-deb --root-owner-group -Zxz --build "$ROOT" "build/$NAME.deb" >/dev/null
rm -rf "$ROOT"
echo "✓ build/$NAME.deb"

if [ "${1:-}" = "--check" ]; then
    dpkg-deb --info "build/$NAME.deb" | sed -n '/Package:/,$p'
    echo "--- contenido"
    dpkg-deb --contents "build/$NAME.deb"
    # Que no se cuele nada del Mac ni ningún .pyc.
    if dpkg-deb --contents "build/$NAME.deb" | grep -E '\.DS_Store|/\._|__pycache__|\.pyc$'; then
        echo "✗ El paquete lleva ficheros que no debería"; exit 1
    fi
    # Que lo empaquetado arranque: se extrae y se ejecuta con un Python moderno.
    TMP=$(mktemp -d)
    dpkg-deb -x "build/$NAME.deb" "$TMP"
    PY=$(command -v python3.13 || command -v python3.14 || command -v python3)
    PYTHONPATH="$TMP/usr/lib/linvideo" "$PY" -m linvideo --version
    PYTHONPATH="$TMP/usr/lib/linvideo" "$PY" -m linvideo --clean-name "Prueba [abc12345].mp4" | tail -1
    rm -rf "$TMP"
    echo "✓ El paquete arranca"
fi
