from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from src.models import AnalysisRecord
from src.storage.repository import Repository


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def repository():
	repo = Repository("sqlite+aiosqlite:///:memory:")
	await repo.init_models()
	yield repo
	await repo.engine.dispose()


def make_record(record_id: str, created_at: datetime, image_path: str) -> AnalysisRecord:
	return AnalysisRecord(
		id=record_id,
		created_at=created_at,
		image_path=image_path,
		ingredients=[{"name": "rice", "grams": 100}],
		totals={"kcal": 130, "protein_g": 2.7},
		status="ok",
	)


async def test_init_models_creates_storage(repository):
	record = make_record("init-1", datetime.now(timezone.utc), "meal.png")

	await repository.save(record)

	saved = await repository.get(record.id)
	assert saved is not None
	assert saved.id == record.id


async def test_save_persists_analysis_record(repository):
	record = make_record("save-1", datetime.now(timezone.utc), "meal.png")

	result = await repository.save(record)

	assert result == record
	saved = await repository.get(record.id)
	assert saved is not None
	assert saved.image_path == record.image_path
	assert saved.ingredients == record.ingredients
	assert saved.totals == record.totals


async def test_get_returns_record_or_none(repository):
	record = make_record("get-1", datetime.now(timezone.utc), "meal.png")
	await repository.save(record)

	found = await repository.get(record.id)

	assert found is not None
	assert found.id == record.id
	assert found.status == "ok"
	assert await repository.get("missing") is None


async def test_list_recent_returns_latest_records_with_limit(repository):
	now = datetime.now(timezone.utc)
	records = [
		make_record("old", now - timedelta(minutes=2), "old.png"),
		make_record("latest", now, "latest.png"),
		make_record("middle", now - timedelta(minutes=1), "middle.png"),
	]
	for record in records:
		await repository.save(record)

	recent = await repository.list_recent(limit=2)

	assert [record.id for record in recent] == ["latest", "middle"]
