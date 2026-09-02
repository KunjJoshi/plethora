# plethora-db/models/pipeline_phase.py
import enum
from sqlalchemy import Column, String, Text, Integer, ForeignKey, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class PhaseType(str, enum.Enum):
    INGESTION = "ingestion"   # runs a function to pull/transform data
    EXECUTION = "execution"   # sends prompt + context to an LLM


class PipelinePhase(Base):
    __tablename__ = 'pipeline_phases'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    agent_slug_id = Column(UUID(as_uuid=True), ForeignKey('agent_slugs.id', ondelete='CASCADE'), nullable=False)
    phase_name = Column(String, nullable=False)
    phase_number = Column(Integer, nullable=False)
    phase_type = Column(Enum(PhaseType), nullable=False)
    prompt = Column(Text, nullable=False)