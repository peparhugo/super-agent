CREATE OR REPLACE FUNCTION prevent_events_modification()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'events table is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS events_prevent_update ON events;
CREATE TRIGGER events_prevent_update
BEFORE UPDATE OR DELETE ON events
FOR EACH ROW
EXECUTE FUNCTION prevent_events_modification();
