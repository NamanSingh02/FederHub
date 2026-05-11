SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;


SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'job_assignments'
ORDER BY ordinal_position;


SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'job_assignments'
ORDER BY indexname;
