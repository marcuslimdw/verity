CREATE TYPE GAMESTATUS AS ENUM ('inactive', 'waiting', 'active');

CREATE TABLE game
(
    id           SERIAL PRIMARY KEY,
    host_id      BIGINT                                       NOT NULL,
    status       GAMESTATUS               DEFAULT ('waiting') NOT NULL,
    when_created TIMESTAMP WITH TIME ZONE DEFAULT (now())     NOT NULL,
    join_code    VARCHAR(6)               DEFAULT ('')        NOT NULL
);

CREATE TABLE signed_user
(
    id      SERIAL PRIMARY KEY                             NOT NULL,
    game_id INTEGER REFERENCES game (id) ON DELETE CASCADE NOT NULL,
    user_id BIGINT                                         NOT NULL,
    UNIQUE (game_id, user_id)
);
