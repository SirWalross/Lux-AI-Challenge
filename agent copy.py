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

DIRECTIONS = Constants.DIRECTIONS
game_state = None

actions = []

logging.basicConfig(filename="log.log", level=logging.INFO, filemode="w")


def get_resource_tiles(map: GameMap, width: int, height: int) -> List[Cell]:
    resource_tiles: List[Cell] = []
    for y in range(height):
        for x in range(width):
            cell = map.get_cell(x, y)
            if cell.has_resource():
                resource_tiles.append(cell)
    return resource_tiles


def find_closest_resource_tile(resource_tiles: List[Cell], player: Player, unit: Unit) -> Optional[Cell]:
    closest_dist = math.inf
    closest_resource_tile = None
    for resource_tile in resource_tiles:
        if resource_tile.resource.type == Constants.RESOURCE_TYPES.COAL and not player.researched_coal():
            continue
        if resource_tile.resource.type == Constants.RESOURCE_TYPES.URANIUM and not player.researched_uranium():
            continue
        dist = resource_tile.pos.distance_to(unit.pos)
        if dist < closest_dist:
            closest_dist = dist
            closest_resource_tile = resource_tile
    return closest_resource_tile


def find_path_to_closest_empty_tile_next_to_city(map: GameMap, player: Player, unit: Unit) -> Optional[Cell]:
    closest_dist = math.inf
    closest_empty_tile = None
    for x in range(map.width):
        for y in range(map.height):
            tile = map.get_cell(x, y)
            if tile.has_resource() or tile.citytile is not None:
                continue
            dist = tile.pos.distance_to(unit.pos)
            if dist < closest_dist:
                closest_dist = dist
                closest_empty_tile = tile
    return closest_empty_tile


def find_closest_city(resource_tiles: List[Cell], player: Player, unit: Unit) -> Optional[CityTile]:
    closest_dist = math.inf
    closest_city_tile = None
    for k, city in player.cities.items():
        for city_tile in city.citytiles:
            dist = city_tile.pos.distance_to(unit.pos)
            if dist < closest_dist:
                closest_dist = dist
                closest_city_tile = city_tile
    return closest_city_tile


def cities_have_enough_foul() -> bool:
    return True


def static_vars(**kwargs):
    def decorate(func):
        for k in kwargs:
            setattr(func, k, kwargs[k])
        return func

    return decorate


def can_move_to(
    moves: Dict[str, Tuple[int, int]], ownUnit: Unit, map: GameMap, dir: DIRECTIONS, units: List[Unit]
) -> bool:
    """
    Check if the unit `ownUnit` can move in direction `dir` 1 step.
    """

    endPosition = Position.translate(ownUnit.pos, dir, 1)
    cell = map.get_cell_by_pos(endPosition)
    key = str(ownUnit.id)
    for unit in units:
        if key in moves:
            pos = moves[key]
            if pos[0] == endPosition.x and pos[1] == endPosition.y:
                if cell.citytile is None or cell.citytile.team != unit.team:
                    return False
        elif unit.pos.x == endPosition.x and unit.pos.y == endPosition.y:
            if cell.citytile is None or cell.citytile.team != unit.team:
                return False
    actions.append(annotate.line(ownUnit.pos.x, ownUnit.pos.y, endPosition.x, endPosition.y))
    logging.info(f"Moving unit {ownUnit.id} to {endPosition.y}, {endPosition.x}, dict: {moves}")
    moves[key] = ownUnit.pos.x, ownUnit.pos.y
    return True


def agent(observation, configuration):
    global game_state

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
    width, height = game_state.map.width, game_state.map.height
    cart_count = len([cart for cart in player.units if not cart.is_worker()])
    worker_count = len(player.units) - cart_count

    global actions
    actions = []
    moves = dict()
    resource_tiles = get_resource_tiles(game_state.map, width, height)

    # we iterate over all our units and do something with them
    for unit in player.units:
        if unit.is_worker() and unit.can_act():
            if unit.get_cargo_space_left() == 0 and cities_have_enough_foul():
                # try and build city
                closest_empty_tile = find_path_to_closest_empty_tile_next_to_city(game_state.map, player, unit)
                if unit.can_build(game_state.map):
                    logging.info(
                        f"Trying to build city with {unit}, Can build {unit.can_build(game_state.map)}, Unit is at"
                        f" {unit.pos.y}, {unit.pos.x}, building city"
                    )
                    actions.append(unit.build_city())
                elif closest_empty_tile is not None and can_move_to(
                    moves, unit, game_state.map, unit.pos.direction_to(closest_empty_tile.pos), player.units
                ):
                    logging.info(
                        f"Trying to build city with {unit}, Can build {unit.can_build(game_state.map)}, Unit is at"
                        f" {unit.pos.y}, {unit.pos.x}, closest empty tile {closest_empty_tile.pos.y},"
                        f" {closest_empty_tile.pos.x}"
                    )
                    actions.append(unit.move(unit.pos.direction_to(closest_empty_tile.pos)))
            elif unit.get_cargo_space_left() > 0:
                # if the unit is a worker and we have space in cargo, lets find the nearest resource tile and try to mine it
                closest_resource_tile = find_closest_resource_tile(resource_tiles, player, unit)
                if closest_resource_tile is not None and can_move_to(
                    moves, unit, game_state.map, unit.pos.direction_to(closest_resource_tile.pos), player.units
                ):
                    actions.append(unit.move(unit.pos.direction_to(closest_resource_tile.pos)))
            else:
                # if unit is a worker and there is no cargo space left, and we have cities, lets return to them
                if len(player.cities) > 0:
                    closest_city_tile = find_closest_city(resource_tiles, player, unit)
                    if closest_city_tile is not None and can_move_to(
                        moves, unit, game_state.map, unit.pos.direction_to(closest_city_tile.pos), player.units
                    ):
                        actions.append(unit.move(unit.pos.direction_to(closest_city_tile.pos)))
    for id, city in player.cities.items():
        for tile in city.citytiles:
            if tile.can_act() and player.city_tile_count > cart_count + worker_count:
                # actions.append(tile.build_worker())
                pass
            elif tile.can_act() and player.city_tile_count > cart_count + worker_count:
                actions.append(tile.build_cart())
            elif tile.can_act():
                actions.append(tile.research())

    return actions
