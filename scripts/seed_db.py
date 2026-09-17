#!/usr/bin/env python3
"""
Seed script to create an admin user for local development.
Run with: python scripts/seed_db.py
"""
import asyncio
import os
import sys
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add the api directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from app.models.user import User, UserRole
from app.config import settings


async def create_admin_user() -> None:
    """Create a default admin user if it doesn't exist."""
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )
    
    async_session_maker = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session_maker() as session:
        # Check if admin user already exists
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.email == "admin@example.com")
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            print("Admin user already exists!")
            print(f"  Email: {existing_user.email}")
            print(f"  Role: {existing_user.role}")
            print(f"  Active: {existing_user.is_active}")
            await engine.dispose()
            return
        
        # Create admin user - pre-hashed bcrypt password for "admin123"
        # Using bcrypt with 12 rounds - this hash was generated with passlib/bcrypt 4.0.1
        hashed_password = "$2b$12$O9yk.35HX37NYMXniaGOJOadPxebgaO3jfo9xdmTHZ0NlUvB9c7ea"
        
        admin_user = User(
            id=str(uuid4()),
            email="admin@example.com",
            hashed_password=hashed_password,
            role=UserRole.admin,
            is_active=True,
        )
        
        session.add(admin_user)
        await session.commit()
        
        print("Admin user created successfully!")
        print(f"  Email: admin@audit-ai.local")
        print(f"  Password: admin123")
        print(f"  Role: admin")
        print()
        print("⚠️  IMPORTANT: Change the default password in production!")
        
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_admin_user())