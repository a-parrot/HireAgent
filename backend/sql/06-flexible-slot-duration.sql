-- Existing databases: run once, or use alembic upgrade head instead.
ALTER TABLE slots
    DROP CHECK ck_slot_duration,
    ADD CONSTRAINT ck_slot_duration CHECK (ends_at > starts_at);
