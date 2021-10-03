import math, sys
from typing import Dict, List, Optional, Tuple
import lux.annotate
from lux.game import Game, GameMap
from lux.game_map import Cell, RESOURCE_TYPES, Position, Resource
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
wood_position = None
coal_position = None

logging.basicConfig(filename="log.log", level=logging.INFO, filemode="w")


def find_tile(pawn: Pawn, radius: int, type: RESOURCE_TYPES) -> Optional[Position]:
    global wood_position
    closest_dist = math.inf
    closest_resource_tile = None
    for resource_tile in gameboard.resource_tiles:
        if resource_tile.resource.type != type:
            continue
        dist = resource_tile.pos.distance_to(pawn.pos)
        if dist < closest_dist and dist > radius:
            closest_dist = dist
            closest_resource_tile = resource_tile
    return closest_resource_tile.pos if closest_resource_tile is not None else None


def find_wood_tile(pawn: Pawn, radius: int):
    global wood_position
    wood_position = find_tile(pawn, radius, Constants.RESOURCE_TYPES.WOOD)


def find_coal_tile(pawn: Pawn, radius: int):
    global coal_position
    coal_position = find_tile(pawn, radius, Constants.RESOURCE_TYPES.COAL)


def move_to_position(pawn: Pawn, position: Position, excludeDir: List[DIRECTIONS] = None) -> Optional[Tile]:
    if excludeDir is None:
        excludeDir = []
    if can_move_to(pawn, pawn.pos.direction_to(position)):
        return gameboard.get_tile_by_pos(pawn.pos.translate(pawn.pos.direction_to(position), 1))
    else:
        direction = pawn.pos.direction_to(position)
        if in_range_pos(pawn.pos.translate(rotate_dir(direction), 1)):
            return gameboard.get_tile_by_pos(pawn.pos.translate(rotate_dir(direction), 1))


def rotate_dir(dir: DIRECTIONS) -> DIRECTIONS:
    if dir == DIRECTIONS.EAST:
        return DIRECTIONS.SOUTH
    if dir == DIRECTIONS.SOUTH:
        return DIRECTIONS.WEST
    if dir == DIRECTIONS.WEST:
        return DIRECTIONS.NORTH
    if dir == DIRECTIONS.NORTH:
        return DIRECTIONS.EAST
    return DIRECTIONS.CENTER


def find_closest_resource_tile(player: Player, pawn: Pawn, excludeDir: List[DIRECTIONS] = None) -> Optional[Tile]:
    # TODO check if it can reach resource tile
    if excludeDir is None:
        excludeDir = []
    closest_dist = math.inf
    closest_resource_tile = None
    for resource_tile in gameboard.resource_tiles:
        if not has_access_to_resource(resource_tile.resource, player):
            continue
        dist = resource_tile.pos.distance_to(pawn.pos)
        if dist < closest_dist and pawn.pos.direction_to(resource_tile.pos) not in excludeDir:
            closest_dist = dist
            closest_resource_tile = resource_tile
    if closest_resource_tile is not None and can_move_to(pawn, pawn.pos.direction_to(closest_resource_tile.pos)):
        return closest_resource_tile
    elif closest_resource_tile is not None:
        return find_closest_resource_tile(player, pawn, [*excludeDir, pawn.pos.direction_to(closest_resource_tile.pos)])


def find_closest_empty_tile_next_to_city(pawn: Pawn) -> Optional[Tile]:
    # TODO check if it can reach empty tile
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


def too_much_fuel(city_tile: CityTile) -> bool:
    """Check if city has enough fuel for the rest of the game"""
    city = gameboard.own_cities.get(city_tile.cityid)

    fuel_needed = city.get_light_upkeep() * night_moves_left()
    if fuel_needed < city.fuel:
        actions.append(annotate.sidetext(f"City {city_tile.cityid} has enough fuel for the whole game"))
    return fuel_needed < city.fuel


def find_closest_city(pawn: Pawn, excludeDir: List[DIRECTIONS] = None) -> Optional[Tile]:
    if excludeDir is None:
        excludeDir = []
    closest_dist = math.inf
    closest_city_tile = None
    for city_tile in gameboard.own_city_tiles:
        dist = city_tile.pos.distance_to(pawn.pos)
        if (
            dist < closest_dist
            and pawn.pos.direction_to(city_tile.pos) not in excludeDir
            and pawn.team == city_tile.team
            and not too_much_fuel(city_tile.citytile)
        ):
            closest_dist = dist
            closest_city_tile = city_tile
    if closest_city_tile is not None and can_move_to(pawn, pawn.pos.direction_to(closest_city_tile.pos)):
        return closest_city_tile
    elif closest_city_tile is not None:
        return find_closest_city(pawn, [*excludeDir, pawn.pos.direction_to(closest_city_tile.pos)])


def cities_have_enough_foul(pawn: Pawn) -> bool:
    # is not night so can assume fuel needed is for 10 moves
    closest_city_tile = find_closest_city(pawn)
    for id, city in gameboard.own_cities.items():
        if (
            city.get_light_upkeep() * 10 > city.fuel
            and closest_city_tile is not None
            and id == closest_city_tile.citytile.cityid
        ):
            return False
    return True


def cities_going_to_have_enough_foul(player: Player, pawn: Pawn) -> bool:
    # first check the proximity for amount of foul
    radius = gameboard.width // 4
    amount_of_fuel = 0
    for x in range(pawn.pos.x - radius, pawn.pos.x + radius + 1):
        for y in range(pawn.pos.y - radius, pawn.pos.y + radius + 1):
            if in_range(x, y) and gameboard.get_tile(x, y).has_resource():
                resource = gameboard.get_tile(x, y).resource
                if has_access_to_resource(resource, player):
                    amount_of_fuel += resource.amount
    amount_of_fuel_needed = 0
    for x in range(pawn.pos.x - radius, pawn.pos.x + radius + 1):
        for y in range(pawn.pos.y - radius, pawn.pos.y + radius + 1):
            if in_range(x, y) and gameboard.get_tile(x, y).has_city():
                city = gameboard.own_cities.get(gameboard.get_tile(x, y).citytile.cityid)
                if city is not None:
                    amount_of_fuel_needed += city.get_light_upkeep() * night_moves_left()

    if amount_of_fuel < amount_of_fuel_needed:
        actions.append(
            annotate.sidetext(
                f"On move {moveCount} at {pawn.pos.x} {pawn.pos.y}  {amount_of_fuel} {amount_of_fuel_needed}"
            )
        )
        for x in range(pawn.pos.x - radius, pawn.pos.x + radius + 1):
            for y in range(pawn.pos.y - radius, pawn.pos.y + radius + 1):
                if in_range(x, y) and gameboard.get_tile(x, y).has_city():
                    city = gameboard.own_cities.get(gameboard.get_tile(x, y).citytile.cityid)
                    if city is not None:
                        actions.append(annotate.x(x, y))
    return amount_of_fuel > amount_of_fuel_needed


def in_range(x: int, y: int):
    return x >= 0 and y >= 0 and x < gameboard.width and y < gameboard.height


def in_range_pos(pos: Position):
    return in_range(pos.x, pos.y)


def can_move_to(ownPawn: Pawn, dir: DIRECTIONS) -> bool:
    """
    Check if the unit `ownUnit` can move in direction `dir` 1 step.
    """

    if dir == DIRECTIONS.CENTER:  # can always stay put
        return True
    endPosition = Position.translate(ownPawn.pos, dir, 1)
    tile = gameboard.get_tile_by_pos(endPosition)
    for pawn in gameboard.pawns:
        if pawn.next_move.x == endPosition.x and pawn.next_move.y == endPosition.y:
            if not tile.has_city() or tile.team != ownPawn.team:
                return False
        elif tile.has_city() and tile.team != ownPawn.team:
            return False
    actions.append(annotate.line(ownPawn.pos.x, ownPawn.pos.y, endPosition.x, endPosition.y))
    logging.info(f"Moving unit {ownPawn.id} to {endPosition.y}, {endPosition.x}")
    ownPawn.next_move = endPosition
    return True


def is_night():
    return (moveCount % 40) >= 30


def night_moves_left():
    # TODO not quite right
    return relu((360 - moveCount) % 40 - 30) + ((360 - moveCount) // 40) * 10


def has_access_to_resource(resource: Resource, player: Player) -> bool:
    if resource.type == Constants.RESOURCE_TYPES.COAL and not player.researched_coal():
        return False
    if resource.type == Constants.RESOURCE_TYPES.URANIUM and not player.researched_uranium():
        return False
    return True


def relu(value: int):
    return 0 if value < 0 else value


def agent(observation, configuration):
    global game_state
    global actions
    global gameboard
    global moveCount
    global wood_position
    global coal_position

    hardCityLimit = 24
    hardUnitLimit = 10

    if moveCount == 0:
        time.sleep(5)

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

    for index, pawn in enumerate(gameboard.own_pawns):
        if pawn.is_worker() and pawn.can_act():
            if index == 0 and moveCount == 39 and len(gameboard.own_pawns) >= 2:
                find_wood_tile(pawn, gameboard.width // 3)
                actions.append(f"Moving to position {wood_position.x} {wood_position.y}")
            elif index == 0 and moveCount == 119 and len(gameboard.own_pawns) >= 2 and wood_position is not None:
                find_wood_tile(pawn, gameboard.width // 2)
                actions.append(f"Moving to position {wood_position.x} {wood_position.y}")
            elif (
                index == 0
                and moveCount == 159
                and len(gameboard.own_pawns) >= 2
                and has_access_to_resource(Resource(Constants.RESOURCE_TYPES.COAL, 1), player)
            ):
                find_coal_tile(pawn, gameboard.width // 2)
                actions.append(f"Moving to position {coal_position.x} {coal_position.y}")
            if index == 0 and wood_position is not None:
                wood_tile = move_to_position(pawn, wood_position)
                if wood_tile is not None:
                    actions.append(pawn.move(pawn.pos.direction_to(wood_tile.pos)))
                    if wood_position.distance_to(pawn.pos) <= 1:
                        wood_position = None
            elif index == 0 and coal_position is not None:
                coal_tile = move_to_position(pawn, coal_position)
                if coal_tile is not None:
                    actions.append(pawn.move(pawn.pos.direction_to(coal_tile.pos)))
                    if coal_position.distance_to(pawn.pos) <= 1:
                        coal_position = None
            elif (
                pawn.get_cargo_space_left() == 0
                and not is_night()
                and cities_have_enough_foul(pawn)
                and cities_going_to_have_enough_foul(player, pawn)
                and hardCityLimit > player.city_tile_count
            ):
                # try and build city
                closest_empty_tile = find_closest_empty_tile_next_to_city(pawn)
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
                if closest_resource_tile is not None:
                    actions.append(pawn.move(pawn.pos.direction_to(closest_resource_tile.pos)))
            else:
                # if unit is a worker and there is no cargo space left, and we have cities, lets return to them
                if len(player.cities) > 0:
                    closest_city_tile = find_closest_city(pawn)
                    if closest_city_tile is not None:
                        actions.append(pawn.move(pawn.pos.direction_to(closest_city_tile.pos)))
    for id, city in player.cities.items():
        for tile in city.citytiles:
            if tile.can_act() and player.city_tile_count > cart_count + worker_count and worker_count < hardUnitLimit:
                actions.append(tile.build_worker())
                worker_count += 1
            elif tile.can_act():
                actions.append(tile.research())

    moveCount += 1
    return actions
