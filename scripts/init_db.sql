-- Execute como superusuário PostgreSQL se o setup.ps1 não conseguir criar automaticamente:
-- psql -U postgres -f scripts\init_db.sql

CREATE ROLE solaris LOGIN PASSWORD 'solaris';
CREATE DATABASE solaris OWNER solaris;
\connect solaris
CREATE EXTENSION IF NOT EXISTS vector;
