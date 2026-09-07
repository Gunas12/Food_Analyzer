from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, JSON, DateTime, select
from datetime import datetime
import uuid

# User #1-in src/models.py faylından gələcək model
from src.models import AnalysisRecord

Base = declarative_base()

class AnalysisRecordModel(Base):
    __tablename__ = "analysis_records"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow)
    image_path = Column(String, nullable=True)
    ingredients = Column(JSON, nullable=True)
    totals = Column(JSON, nullable=True)

class Repository:
    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url, echo=False)
        self.SessionLocal = async_sessionmaker(bind=self.engine, expire_on_commit=False)

    async def init_models(self) -> None:
        # cədvəli yaradır (yoxdursa)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def save(self, record: AnalysisRecord) -> AnalysisRecord:
        # DB-yə yazır, id və created_at doldurur
        async with self.SessionLocal() as session:
            db_record = AnalysisRecordModel(
                id=record.id,
                created_at=record.created_at,
                image_path=record.image_path,
                ingredients=record.ingredients,
                totals=record.totals
            )
            session.add(db_record)
            await session.commit()
            return record

    async def get(self, record_id: str) -> AnalysisRecord | None:
        # tək qeydi id ilə qaytarır
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(AnalysisRecordModel).where(AnalysisRecordModel.id == record_id)
            )
            db_record = result.scalars().first()
            if db_record:
                return AnalysisRecord(
                    id=db_record.id,
                    created_at=db_record.created_at,
                    image_path=db_record.image_path,
                    ingredients=db_record.ingredients,
                    totals=db_record.totals,
                    status="ok"
                )
            return None

    async def list_recent(self, limit: int = 20) -> list[AnalysisRecord]:
        # ən son N analizi qaytarır
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(AnalysisRecordModel).order_by(AnalysisRecordModel.created_at.desc()).limit(limit)
            )
            db_records = result.scalars().all()
            return [
                AnalysisRecord(
                    id=r.id,
                    created_at=r.created_at,
                    image_path=r.image_path,
                    ingredients=r.ingredients,
                    totals=r.totals,
                    status="ok"
                ) for r in db_records
            ]