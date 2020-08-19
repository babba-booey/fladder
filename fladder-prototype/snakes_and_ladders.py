import logging
import cachetools
import secrets
import json

from uuid import uuid4
from redis import Redis

logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] - [%(name)s] %(levelname)s - %(funcName)s - %(message)s")

ACTIVE_GAMES = "ACTIVE_GAMES"
DIE_CASTS = "DIE_CASTS_{game_id}"
PLAYER_NAME_SEPARATOR = ':'
# REDIS = Redis(host='localhost', port=6379)
DIE_FACES = [1, 2, 3, 4, 5, 6]

@cachetools.cached({})
def get_logger(name=None):
    return logging.getLogger(name)


@cachetools.cached({})
def redis_connection(game_id):
    return Redis(host='localhost', port=6379)


class Game(object):
    def __init__(self, player_names):
        game_uuid = str(uuid4())
        self.game_id = "game_{}".format(game_uuid)
        self.player_names = player_names
        players_list = PLAYER_NAME_SEPARATOR.join(sorted(player_names, key=lambda x: x))
        self.logger = get_logger(self.game_id)
        existing_game_id = str(redis_connection(self.game_id).hget(ACTIVE_GAMES, players_list))
        self.logger.info("Looked within Redis for an existing game session with players - %s. Session found: %s", players_list, existing_game_id)
        if not existing_game_id or existing_game_id == "None":
            self.logger.info("Game ID: %s, players list: %s", self.game_id, players_list)
            redis_connection(self.game_id).hset(ACTIVE_GAMES, players_list, self.game_id)
            self.logger.info("Game session created")
        else:
            self.logger.warning("Players %s are already in an active game session %s" %(player_names, existing_game_id))
            self.game_id = existing_game_id
            self.logger.info("Resuming game session")


    def roll_dice(self, player):
        if player not in self.player_names:
            self.logger.warning("Player %s not allowed in this game", player)
            return -1
        obtained_face = secrets.choice(DIE_FACES)
        redis_key = DIE_CASTS.format(game_id=self.game_id)
        self.logger.info("Die cast by player %s. Face obtained: %s. Destination redis key: %s", player, obtained_face, redis_key)
        redis_connection(self.game_id).lpush(redis_key, json.dumps({"player_name": player, "face": obtained_face}))


players = ["alice", "daniel", "bob", "carol"]
game_session = Game(players)
game_session.roll_dice(players[0])
