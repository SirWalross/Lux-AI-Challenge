import math, sys
from typing import Dict, List, Optional, Tuple
import lux.annotate
from lux.game import Game, GameMap
from lux.game_map import Cell, RESOURCE_TYPES, Position
from lux.constants import Constants
from lux.game_constants import GAME_CONSTANTS
from lux import annotate
from lux.game_objects import CityTile, Player, Unit
import logging
import time
from classes import *


DIRECTIONS = Constants.DIRECTIONS
game_state = None

actions = []
gameboard: GameBoard = None
moveCount = 0

logging.basicConfig(filename="log.log", level=logging.INFO, filemode="w")


def find_closest_resource_tile(player: Player, pawn: Pawn) -> Optional[Tile]:
    closest_dist = math.inf
    closest_resource_tile = None
    for resource_tile in gameboard.resource_tiles:
        if resource_tile.resource.type == Constants.RESOURCE_TYPES.COAL and not player.researched_coal():
            continue
        if resource_tile.resource.type == Constants.RESOURCE_TYPES.URANIUM and not player.researched_uranium():
            continue
        dist = resource_tile.pos.distance_to(pawn.pos)
        if dist < closest_dist:
            closest_dist = dist
            closest_resource_tile = resource_tile
    return closest_resource_tile


def find_path_to_closest_empty_tile_next_to_city(pawn: Pawn) -> Optional[Tile]:
    closest_dist = math.inf
    closest_empty_tile = None
    for x in range(gameboard.width):
        for y in range(gameboard.height):
            tile = gameboard.get_tile(x, y)
            if tile.has_resource() or tile.has_city():
                continue
            dist = tile.pos.distance_to(pawn.pos)
            if dist < closest_dist:
                closest_dist = dist
                closest_empty_tile = tile
    return closest_empty_tile


def find_closest_city(pawn: Pawn) -> Optional[Tile]:
    closest_dist = math.inf
    closest_city_tile = None
    for city_tile in gameboard.city_tiles:
        dist = city_tile.pos.distance_to(pawn.pos)
        if dist < closest_dist:
            closest_dist = dist
            closest_city_tile = city_tile
    return closest_city_tile


def cities_have_enough_foul() -> bool:
    return True


def can_move_to(ownPawn: Pawn, dir: DIRECTIONS) -> bool:
    """
    Check if the unit `ownUnit` can move in direction `dir` 1 step.
    """

    endPosition = Position.translate(ownPawn.pos, dir, 1)
    tile = gameboard.get_tile_by_pos(endPosition)
    for pawn in gameboard.pawns:
        if pawn.next_move.x == endPosition.x and pawn.next_move.y == endPosition.y:
            if tile.has_city() or tile.team != pawn.team:
                return False
    actions.append(annotate.line(ownPawn.pos.x, ownPawn.pos.y, endPosition.x, endPosition.y))
    logging.info(f"Moving unit {ownPawn.id} to {endPosition.y}, {endPosition.x}")
    ownPawn.next_move = endPosition
    return True


def agent(observation, configuration):
    global game_state
    global actions
    global gameboard
    global moveCount

    if moveCount == 0:
        time.sleep(10)

    moveCount += 1

    ### Do not edit ###
    if observation["step"] == 0:
        game_state = Game()
        game_state._initialize(observation["updates"])
        game_state._update(observation["updates"][2:])
        game_state.id = observation.player
    else:
        game_state._update(observation["updates"])

    ### AI Code goes down here! ###
    player = game_state.players[observation.player]
    opponent = game_state.players[(observation.player + 1) % 2]
    cart_count = len([cart for cart in player.units if not cart.is_worker()])
    worker_count = len(player.units) - cart_count

    actions = []
    gameboard = GameBoard(game_state, observation)

    # we iterate over all our units and do something with them
    for pawn in gameboard.own_pawns:
        if pawn.is_worker() and pawn.can_act():
            if pawn.get_cargo_space_left() == 0 and cities_have_enough_foul():
                # try and build city
                closest_empty_tile = find_path_to_closest_empty_tile_next_to_city(pawn)
                if pawn.can_build(game_state.map):
                    logging.info(
                        f"Trying to build city with {pawn}, Can build {pawn.can_build(game_state.map)}, Unit is at"
                        f" {pawn.pos.y}, {pawn.pos.x}, building city"
                    )
                    actions.append(pawn.build_city())
                elif closest_empty_tile is not None and can_move_to(
                    pawn, pawn.pos.direction_to(closest_empty_tile.pos)
                ):
                    logging.info(
                        f"Trying to build city with {pawn}, Can build {pawn.can_build(game_state.map)}, Unit is at"
                        f" {pawn.pos.y}, {pawn.pos.x}, closest empty tile {closest_empty_tile.pos.y},"
                        f" {closest_empty_tile.pos.x}"
                    )
                    actions.append(pawn.move(pawn.pos.direction_to(closest_empty_tile.pos)))
            elif pawn.get_cargo_space_left() > 0:
                # if the unit is a worker and we have space in cargo, lets find the nearest resource tile and try to mine it
                closest_resource_tile = find_closest_resource_tile(player, pawn)
                if closest_resource_tile is not None and can_move_to(
                    pawn, pawn.pos.direction_to(closest_resource_tile.pos)
                ):
                    actions.append(pawn.move(pawn.pos.direction_to(closest_resource_tile.pos)))
            else:
                # if unit is a worker and there is no cargo space left, and we have cities, lets return to them
                if len(player.cities) > 0:
                    closest_city_tile = find_closest_city(pawn)
                    if closest_city_tile is not None and can_move_to(
                        pawn, pawn.pos.direction_to(closest_city_tile.pos)
                    ):
                        actions.append(pawn.move(pawn.pos.direction_to(closest_city_tile.pos)))
    for id, city in player.cities.items():
        for tile in city.citytiles:
            if tile.can_act() and player.city_tile_count > cart_count + worker_count:
                actions.append(tile.build_worker())
            elif tile.can_act() and player.city_tile_count > cart_count + worker_count:
                actions.append(tile.build_cart())
            elif tile.can_act():
                actions.append(tile.research())

    return actions
