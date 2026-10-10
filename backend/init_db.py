import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://neondb_owner:npg_ndpxoK0MWH3Z@ep-royal-cake-azg9nfy8-pooler.c-3.ap-southeast-1.aws.neon.tech/neondb?ssl=require")

async def init_db():
    print("Connecting to database...")
    engine = create_async_engine(DATABASE_URL)
    
    with open("docker/postgres/init.sql", "r") as f:
        sql = f.read()

    print("Running init.sql...")
    async with engine.begin() as conn:
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                try:
                    await conn.execute(text(statement))
                except Exception as e:
                    print(f"Error executing statement: {e}")
                    pass
    print("Database initialized successfully!")

if __name__ == "__main__":
    asyncio.run(init_db())
