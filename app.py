import sys

try:
    from gui import JarvisGUI
except ImportError as e:
    print(f"Missing dependency: {e}\nRun: pip install -r requirements.txt")
    sys.exit(1)

if __name__ == "__main__":
    JarvisGUI().run()
