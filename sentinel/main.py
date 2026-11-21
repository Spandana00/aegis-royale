"""AEGIS competition entrypoint; intact attributed Sentinel policy."""
from .combat import Combat
from . import mechfight as mf

if __name__ == "__main__":
    mf.run(Combat)
