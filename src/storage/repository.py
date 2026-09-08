from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, Boolean, String, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from src.models import AnalysisRecord

Base = declarative_base()


class AnalysisRecordModel(Base):
    __tablename__ = "analysis_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    image_path = Column(String, nullable=False)
    meal_recognized = Column(Boolean, nullable=False, default=True)
    ingredients = Column(JSON, nullable=False, default=list)
    totals = Column(JSON, nullable=False, default=dict)


class Repository:
    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url, echo=False)
        self.SessionLocal = async_sessionmaker(bind=self.engine, expire_on_commit=False)

    async def init_models(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def save(self, record: AnalysisRecord) -> AnalysisRecord:
        async with self.SessionLocal() as session:
            db_record = AnalysisRecordModel(
                image_path=record.image_path,
                meal_recognized=record.meal_recognized,
                ingredients=[ing.model_dump() for ing in record.ingredients],
                totals=record.totals.model_dump(),
            )
            session.add(db_record)
            await session.commit()
            await session.refresh(db_record)

            # pydantic's own "copy with updated fields" — cleaner than
            # rebuilding a fresh AnalysisRecord by hand.
            return record.model_copy(
                update={"id": db_record.id, "created_at": db_record.created_at}
            )

    async def get(self, record_id: int) -> AnalysisRecord | None:
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(AnalysisRecordModel).where(AnalysisRecordModel.id == record_id)
            )
            db_record = result.scalars().first()
            if db_record is None:
                return None
            return AnalysisRecord(
                id=db_record.id,
                created_at=db_record.created_at,
                image_path=db_record.image_path,
                meal_recognized=db_record.meal_recognized,
                ingredients=db_record.ingredients,
                totals=db_record.totals,
            )

    async def list_recent(self, limit: int = 20) -> list[AnalysisRecord]:
        # Avoid hitting the DB at all for a non-positive limit.
        if limit <= 0:
            return []

        async with self.SessionLocal() as session:
            result = await session.execute(
                select(AnalysisRecordModel)
                # id DESC as a tiebreaker keeps ordering deterministic when
                # two rows share the same created_at timestamp.
                .order_by(
                    AnalysisRecordModel.created_at.desc(),
                    AnalysisRecordModel.id.desc(),
                )
                .limit(limit)
            )
            db_records = result.scalars().all()
            return [
                AnalysisRecord(
                    id=r.id,
                    created_at=r.created_at,
                    image_path=r.image_path,
                    meal_recognized=r.meal_recognized,
                    ingredients=r.ingredients,
                    totals=r.totals,
                )
                for r in db_records
            ]