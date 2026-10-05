"""Load DE-SynPUF beneficiary and claims files into member-year and claim tables."""

from .pipeline import create_pipeline

__all__ = ["create_pipeline"]
