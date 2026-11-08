-- Record the score each cached explanation describes (the text quotes it). When a later
-- score run changes that cell-hour's score, the cached text no longer matches and is
-- regenerated; unchanged scores keep their explanation across hourly re-scores.
-- Rows written before this column existed never match and are replaced on the next write.
ALTER TABLE score_explanations ADD COLUMN IF NOT EXISTS explained_score real;
