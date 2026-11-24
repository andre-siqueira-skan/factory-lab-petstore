import os
import tempfile

# Point the app at a throwaway SQLite file before app.db creates its engine.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
