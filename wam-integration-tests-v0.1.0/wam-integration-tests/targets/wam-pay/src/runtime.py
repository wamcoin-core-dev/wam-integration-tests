import os
from pathlib import Path

from src.errors import ConflictError


class InstanceLock:
    """OS-held lock is released on crash; lock-file existence is not a lock."""
    def __init__(self, database):
        path = Path(database + ".lock")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0, 2)
                if self.file.tell() == 0:
                    self.file.write(b"0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise ConflictError("Another process is using this database") from None

    def close(self):
        self.file.close()
