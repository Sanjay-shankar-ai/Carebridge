import asyncio
from sqlalchemy import text
from app.database.session import async_session_factory

async def sync():
    statements = [
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS status VARCHAR(32) DEFAULT 'delivered';",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS max_retries INTEGER DEFAULT 3;",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS last_error TEXT;",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ;",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ;",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS action_link VARCHAR(255);",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255);",
        "ALTER TABLE care_cases ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;",
        "ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;",
        "ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS role VARCHAR(32);",
        "ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS title VARCHAR(255);",
        "ALTER TABLE conversation_sessions ALTER COLUMN patient_id DROP NOT NULL;",
        "ALTER TABLE communications ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;",
        "ALTER TABLE communications ADD COLUMN IF NOT EXISTS role VARCHAR(32);",
        "ALTER TABLE communications ALTER COLUMN case_id DROP NOT NULL;",
        "ALTER TABLE communications ALTER COLUMN patient_id DROP NOT NULL;",
    ]
    async with async_session_factory() as session:
        for stmt in statements:
            try:
                await session.execute(text(stmt))
                print(f"Executed: {stmt[:50]}...")
            except Exception as e:
                print(f"Error executing {stmt[:50]}: {e}")
        await session.commit()
    print("Schema sync complete.")

if __name__ == "__main__":
    asyncio.run(sync())
