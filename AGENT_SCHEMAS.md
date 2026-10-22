# Agentic AI Data Analysis System — Schema Contracts

## 1. Purpose

This document defines the shared data contracts used across the Agentic AI Data Analysis System.

The schemas are the single source of truth for communication between:

- Orchestrator Agent
- SQL Agent
- Analysis Agent
- Visualization Service
- Report Agent
- Python Orchestration Controller
- API / Frontend

The purpose of these contracts is to ensure that every component agrees on:

- What data it receives
- What data it produces
- Which fields are required
- Which fields are optional
- What each field means
- How errors and warnings are represented
- How requests are tracked across the entire system

The actual executable schemas are implemented using Pydantic in:

```text
