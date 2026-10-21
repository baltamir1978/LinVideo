"""Punto de entrada: con argumentos, consola; sin ellos, la ventana."""

import sys


def main() -> int:
    args = sys.argv[1:]
    if args:
        from . import cli
        return cli.main(args)
    # La interfaz GTK todavía no está escrita (21-oct-2026).
    print("La ventana de LinVideo todavía no existe; de momento, sólo el modo consola.\n"
          "Prueba: linvideo --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
