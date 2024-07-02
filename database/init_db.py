# init_db.py
from database import engine, metadata

metadata.create_all(engine)
