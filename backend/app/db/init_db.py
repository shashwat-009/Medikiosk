from app.db.database import Base, engine

# Import all models so SQLAlchemy registers them with Base.metadata.
from app.models.patient import Patient
from app.models.session import Session
from app.models.response import Response
from app.models.doctor import Doctor


def init_db():
    Base.metadata.create_all(bind=engine)