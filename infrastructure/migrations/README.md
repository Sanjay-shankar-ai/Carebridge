# Database Migrations

CareBridge uses Alembic for database schema migrations and versioning.

## Commands

Initialize migration environment:
```bash
cd backend
alembic init -t async migrations
```

Generate a migration:
```bash
alembic revision --autogenerate -m "create_initial_carebridge_tables"
```

Apply migrations:
```bash
alembic upgrade head
```

Rollback a migration:
```bash
alembic downgrade -1
```
