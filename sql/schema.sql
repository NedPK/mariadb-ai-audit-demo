CREATE TABLE IF NOT EXISTS documents (
  id BIGINT NOT NULL AUTO_INCREMENT,
  source VARCHAR(512) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS chunks (
  id BIGINT NOT NULL AUTO_INCREMENT,
  document_id BIGINT NOT NULL,
  chunk_index INT NOT NULL,
  content TEXT NOT NULL,
  embedding VECTOR(1536) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_chunks_document_id FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS retrieval_requests (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id VARCHAR(256) NULL,
  feature VARCHAR(128) NULL,
  source VARCHAR(128) NULL,
  query TEXT NOT NULL,
  k INT NOT NULL,
  embedding_model VARCHAR(128) NOT NULL,
  query_embedding VECTOR(1536) NOT NULL,
  candidates_returned INT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS retrieval_candidates (
  id BIGINT NOT NULL AUTO_INCREMENT,
  request_id BIGINT NOT NULL,
  rank INT NOT NULL,
  chunk_id BIGINT NOT NULL,
  score DOUBLE NOT NULL,
  document_id BIGINT NOT NULL,
  chunk_index INT NOT NULL,
  content TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_retrieval_candidates_request_id FOREIGN KEY (request_id) REFERENCES retrieval_requests(id),
  CONSTRAINT fk_retrieval_candidates_chunk_id FOREIGN KEY (chunk_id) REFERENCES chunks(id)
);

CREATE TABLE IF NOT EXISTS retrieval_exposures (
  id BIGINT NOT NULL AUTO_INCREMENT,
  request_id BIGINT NOT NULL,
  kind VARCHAR(64) NOT NULL,
  content MEDIUMTEXT NOT NULL,
  chunks_exposed INT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_retrieval_exposures_request_id FOREIGN KEY (request_id) REFERENCES retrieval_requests(id)
);

CREATE TABLE IF NOT EXISTS retrieval_exposure_chunks (
  id BIGINT NOT NULL AUTO_INCREMENT,
  exposure_id BIGINT NOT NULL,
  request_id BIGINT NOT NULL,
  rank INT NOT NULL,
  chunk_id BIGINT NOT NULL,
  score DOUBLE NOT NULL,
  document_id BIGINT NOT NULL,
  chunk_index INT NOT NULL,
  content TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_retrieval_exposure_chunks_exposure_id FOREIGN KEY (exposure_id) REFERENCES retrieval_exposures(id),
  CONSTRAINT fk_retrieval_exposure_chunks_request_id FOREIGN KEY (request_id) REFERENCES retrieval_requests(id),
  CONSTRAINT fk_retrieval_exposure_chunks_chunk_id FOREIGN KEY (chunk_id) REFERENCES chunks(id)
);
