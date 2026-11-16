-- Existing SQL-initialized databases only. Alternatively use Alembic upgrade head.
ALTER TABLE slots DROP INDEX uk_slot_batch_start;
