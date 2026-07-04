-- HSK Vocabulary Frequency Database Schema

CREATE TABLE IF NOT EXISTS hsk_wordlist (
    id SERIAL PRIMARY KEY,
    word VARCHAR(50) NOT NULL UNIQUE,
    pinyin VARCHAR(100),
    hsk_level SMALLINT NOT NULL CHECK (hsk_level BETWEEN 1 AND 9),
    definition TEXT,
    definition_th TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS exam_sources (
    id SERIAL PRIMARY KEY,
    exam_id VARCHAR(100) NOT NULL,
    year SMALLINT,
    source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('reading', 'listening')),
    hsk_level SMALLINT CHECK (hsk_level BETWEEN 1 AND 9),
    filename VARCHAR(255),
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (exam_id, source_type)
);

CREATE TABLE IF NOT EXISTS word_frequencies (
    id SERIAL PRIMARY KEY,
    word VARCHAR(50) NOT NULL,
    hsk_level SMALLINT,
    source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('reading', 'listening')),
    exam_id VARCHAR(100) NOT NULL,
    frequency INTEGER NOT NULL DEFAULT 1,
    in_official_wordlist BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (word, source_type, exam_id),
    FOREIGN KEY (exam_id, source_type) REFERENCES exam_sources(exam_id, source_type)
);

CREATE TABLE IF NOT EXISTS frequency_aggregates (
    id SERIAL PRIMARY KEY,
    word VARCHAR(50) NOT NULL,
    hsk_level SMALLINT,
    source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('reading', 'listening', 'all')),
    total_frequency INTEGER NOT NULL DEFAULT 0,
    exam_count INTEGER NOT NULL DEFAULT 0,
    in_official_wordlist BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (word, source_type)
);

-- Sentences extracted from raw exam texts, for example-sentence lookup.
CREATE TABLE IF NOT EXISTS exam_sentences (
    id SERIAL PRIMARY KEY,
    exam_id VARCHAR(100) NOT NULL,
    source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('reading', 'listening')),
    sentence TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (exam_id, source_type, sentence),
    FOREIGN KEY (exam_id, source_type) REFERENCES exam_sources(exam_id, source_type)
);

CREATE INDEX IF NOT EXISTS idx_wf_word ON word_frequencies(word);
CREATE INDEX IF NOT EXISTS idx_wf_hsk_level ON word_frequencies(hsk_level);
CREATE INDEX IF NOT EXISTS idx_wf_source_type ON word_frequencies(source_type);
CREATE INDEX IF NOT EXISTS idx_fa_hsk_level ON frequency_aggregates(hsk_level);
CREATE INDEX IF NOT EXISTS idx_fa_source_type ON frequency_aggregates(source_type);
CREATE INDEX IF NOT EXISTS idx_fa_total_freq ON frequency_aggregates(total_frequency DESC);
