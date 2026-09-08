import pytest
import pytest_asyncio

from src.models import AnalysisRecord, IngredientLine, MealTotals
from src.storage.repository import Repository


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def repository():
	repo = Repository("sqlite+aiosqlite:///:memory:")
	await repo.init_models()
	yield repo
	await repo.engine.dispose()


def make_record(image_path: str, meal_recognized: bool = True) -> AnalysisRecord:
	return AnalysisRecord(
		id=None,
		image_path=image_path,
		meal_recognized=meal_recognized,
		ingredients=[
			IngredientLine(
				name="rice",
				estimated_grams=100,
				confidence=0.95,
				kcal=130,
				protein_g=2.7,
				carbs_g=28,
				fat_g=0.3,
			)
		],
		totals=MealTotals(kcal=130, protein_g=2.7, carbs_g=28, fat_g=0.3),
	)


async def test_init_models_creates_storage(repository):
	record = make_record("meal.png")

	await repository.save(record)

	saved = await repository.get(1)
	assert saved is not None
	assert saved.id == 1


async def test_save_persists_analysis_record(repository):
	record = make_record("meal.png", meal_recognized=False)

	result = await repository.save(record)

	assert result.id is not None
	saved = await repository.get(result.id)
	assert saved is not None
	assert saved.id == result.id
	assert saved.image_path == record.image_path
	assert saved.meal_recognized is False
	assert saved.ingredients == record.ingredients
	assert saved.totals == record.totals


async def test_get_returns_record_or_none(repository):
	record = await repository.save(make_record("meal.png"))

	found = await repository.get(record.id)

	assert found is not None
	assert found.id == record.id
	assert found.meal_recognized is True
	assert await repository.get(999) is None


async def test_list_recent_returns_latest_records_with_limit(repository):
	records = [
		await repository.save(make_record("old.png")),
		await repository.save(make_record("middle.png")),
		await repository.save(make_record("latest.png")),
	]

	recent = await repository.list_recent(limit=2)

	assert [record.id for record in recent] == [records[2].id, records[1].id]
