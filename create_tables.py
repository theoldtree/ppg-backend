"""
Create database tables
"""
from app.db.database import Base, engine
from app.db.models import (
    User,
    Measurement,
    PPGProcessedData,
    QCFeedback,
    AnalysisResult,
    UserBaseline,
    DemographicBaseline,
    Notification,
)

if __name__ == "__main__":
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✓ Tables created successfully!")
