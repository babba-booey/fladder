import logging
import cachetools
import secrets
import json

from uuid import uuid4
from redis import Redis
from itertools import cycle
from datetime import datetime

logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] - [%(name)s] %(levelname)s - %(funcName)s - %(message)s")

ACTIVE_GAMES = "ACTIVE_GAMES"
DIE_CASTS = "{game_id}:DIE_CASTS"
MAX_WINNERS = "{game_id}:MAX_WINNERS"
PLAYER_POSITIONS = "{game_id}:PLAYER_POSITIONS"
PLAYER_NAME_SEPARATOR = ':'

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
        t_now = datetime.utcnow().strftime("%s")
        self.game_id = "game_{uuid}_{timestamp}".format(uuid=game_uuid, timestamp=t_now)
        self.player_names = player_names
        self.logger = get_logger(self.game_id)

        self.die_casts = DIE_CASTS.format(game_id=self.game_id)
        self.player_positions = PLAYER_POSITIONS.format(game_id=self.game_id)

        players_list = PLAYER_NAME_SEPARATOR.join(sorted(player_names, key=lambda x: x))
        existing_game_id = redis_connection(self.game_id).hget(ACTIVE_GAMES, players_list)
        if not existing_game_id:
            self.logger.info("Game ID: %s, players list: %s", self.game_id, players_list)
            redis_connection(self.game_id).hset(ACTIVE_GAMES, players_list, self.game_id)
            self.logger.info("Game session created")
            for player in self.player_names:
                redis_connection(self.game_id).hset(self.player_positions, player, 0)
                self.logger.info("Initialized player position for player %s", player)
        else:
            existing_game_id = existing_game_id.decode("UTF-8")
            self.logger.info("Looked within Redis for an existing game session with players - %s. Session found: %s", players_list, existing_game_id)
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
        redis_connection(self.game_id).rpush(redis_key, json.dumps({"player_name": player, "face": obtained_face}))
        return obtained_face


    def update_player_position(self, player, die_face):
        current_player_position = self.player_current_position(player)
        next_player_position = None
        if current_player_position == 0:
            if die_face == 6:
                next_player_position = 1
                redis_connection(self.game_id).hset(self.player_positions, player, next_player_position)
                self.logger.info("Setting player position to 1 because 6 was rolled and player was at position 0")
            else:
                self.logger.info("Not updating player position. Currently at 0, rolled %s", die_face)
            return
        next_player_position = current_player_position + die_face
        if next_player_position > 100:
            self.logger.info("Not updating player position. Next position %s is outside board", next_player_position)
            return

        redis_connection(self.game_id).hset(self.player_positions, player, next_player_position)
        self.logger.info("Updated player %s. previous position: %s, now: %s", player, current_player_position, next_player_position)


    def player_current_position(self, player):
        if not self.player_positions:
            return 0
        current_pos = redis_connection(self.game_id).hget(self.player_positions, player)
        if not current_pos:
            return 0
        return int(current_pos)


def start_game():
    players = {
        "alice": {
            "status": "not-started"
        },
        "bob": {
            "status": "not-started"
        },
        "cindy": {
            "status": "not-started"
        },
        "daniel": {
            "status": "not-started"
        }
    }
    game_session = Game(players.keys())

    cycles_passed = 1
    logger = get_logger(__name__)

    active_players = players.keys()
    player_cycle = cycle(active_players)
    podium = []

    try:
        logger.info("Players playing: %s", [x for x in players.keys()])
        player = next(player_cycle)
        while player and player_cycle:
            logger.info("Current player: %s", player)
            obtained_face = game_session.roll_dice(player=player)
            game_session.update_player_position(player=player, die_face=obtained_face)
            current_position = game_session.player_current_position(player=player)
            if current_position == 100:
                del players[player]
                podium.append(player)
                logger.info("Removed player %s from upcoming cycle. Players in upcoming cycle: %s", player, active_players)
                active_players = players.keys()
                player_cycle = cycle(active_players)
                if len(active_players) == 1:
                    logger.info("No more competitors. Losing player: %s", active_players)
                    break
            player = next(player_cycle)
            cycles_passed += 1

    except KeyboardInterrupt:
        logger.warning("Received keypress")
        logger.info("Cycles passed: %s", cycles_passed)


    except Exception as exp:
        logger.exception("An error occured: %s", exp)

    logger.info("Game over. Cycles passed: %s", cycles_passed)
    logger.info("Podium: %s", podium)


if __name__ == "__main__":
    start_game()
