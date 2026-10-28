# Import models so SQLAlchemy registers them with Base.metadata on startup
from app.modules.chat import models as _chat_models  # noqa: F401
