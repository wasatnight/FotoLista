import sys

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--diagnostico":
        from diagnostico import run
        run(sys.argv[2])
    else:
        from fotolista.ui import run
        run()
