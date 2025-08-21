from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, UniqueConstraint
from datetime import datetime

DATABASE_URL = "sqlite+aiosqlite:///./data.db"

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    event_type = Column(String(32))
    ts = Column(DateTime, default=datetime.utcnow)
    brand = Column(String(120), nullable=True)
    line = Column(String(160), nullable=True)
    size = Column(String(80), nullable=True)
    retailer = Column(String(120), nullable=True)
    state = Column(String(8), nullable=True)
    delivered_cents = Column(BigInteger, nullable=True)

class PricePoint(Base):
    __tablename__ = "price_points"
    id = Column(Integer, primary_key=True)
    day = Column(String(10))  # YYYY-MM-DD
    brand = Column(String(120))
    line = Column(String(160))
    size = Column(String(80))
    delivered_cents = Column(BigInteger)
    source = Column(String(64), default="cheapest")  # cheapest|retailer:<key>
    __table_args__ = (UniqueConstraint("day","brand","line","size","source", name="uix_pp_day_sku_source"),)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session():
    async with AsyncSessionLocal() as session:
        yield session
