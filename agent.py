import math
from typing import List, Optional, Tuple
import logging
import time
from lux.game import Game
from lux.game_map import RESOURCE_TYPES, Position, Resource
from lux.constants import Constants
from lux import annotate
from lux.game_objects import CityTile, Player
from classes import Pawn, GameBoard, Tile


DIRECTIONS = Constants.DIRECTIONS
game_state = None

actions = []
gameboard: GameBoard = None
moveCount = 0
wood_position = None
coal_position = None

HARD_CITY_LIMIT = 40
HARD_UNIT_LIMIT = 10

logging.basicConfig(filename="log.log", level=logging.INFO, filemode="w")


def find_tile(pawn: Pawn, radius: int, resource_type: RESOURCE_TYPES) -> Optional[Position]:
    global wood_position
    closest_dist = math.inf
    closest_resource_tile = None
    for resource_tile in gameboard.resource_tiles:
        if resource_tile.resource.type != resource_type:
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
    return None


def rotate_dir(direction: DIRECTIONS) -> DIRECTIONS:
    if direction == DIRECTIONS.EAST:
        return DIRECTIONS.SOUTH
    if direction == DIRECTIONS.SOUTH:
        return DIRECTIONS.WEST
    if direction == DIRECTIONS.WEST:
        return DIRECTIONS.NORTH
    if direction == DIRECTIONS.NORTH:
        return DIRECTIONS.EAST
    return DIRECTIONS.CENTER


def find_closest_resource_tile(player: Player, pawn: Pawn, exclude_dir: List[DIRECTIONS] = None) -> Optional[Tile]:
    # TODO check if it can reach resource tile
    if exclude_dir is None:
        exclude_dir = []
    closest_dist = math.inf
    closest_resource_tile = None
    for resource_tile in gameboard.resource_tiles:
        if not has_access_to_resource(resource_tile.resource, player):
            continue
        dist = resource_tile.pos.distance_to(pawn.pos)
        if dist < closest_dist and pawn.pos.direction_to(resource_tile.pos) not in exclude_dir:
            closest_dist = dist
            closest_resource_tile = resource_tile
    if closest_resource_tile is not None and can_move_to(pawn, pawn.pos.direction_to(closest_resource_tile.pos)):
        return closest_resource_tile
    elif closest_resource_tile is not None:
        return find_closest_resource_tile(
            player, pawn, [*exclude_dir, pawn.pos.direction_to(closest_resource_tile.pos)]
        )
    return None


def find_closest_empty_tile(pawn: Pawn, exclude_dir: List[DIRECTIONS] = None) -> Optional[Tile]:
    # TODO check if it can reach empty tile
    if exclude_dir is None:
        exclude_dir = []
    closest_dist = math.inf
    closest_empty_tile = None
    for x in range(gameboard.width):
        for y in range(gameboard.height):
            tile = gameboard.get_tile(x, y)
            if tile.has_resource() or tile.has_city():
                continue
            dist = tile.pos.distance_to(pawn.pos) * (2 if not neighbouring_city(tile, pawn.team) else 1) * (1.2 if not neighbouring_resource(tile) else 1)
            if dist < closest_dist and pawn.pos.direction_to(tile.pos) not in exclude_dir:
                closest_dist = dist
                closest_empty_tile = tile
    if closest_empty_tile is not None and can_move_to(pawn, pawn.pos.direction_to(closest_empty_tile.pos)):
        return closest_empty_tile
    elif closest_empty_tile is not None:
        return find_closest_empty_tile(pawn, [*exclude_dir, pawn.pos.direction_to(closest_empty_tile.pos)])
    return None


def neighbouring_city(tile: Tile, team: int) -> bool:
    for x in [tile.pos.x - 1, tile.pos.x + 1]:
        for y in [tile.pos.y - 1, tile.pos.y + 1]:
            if in_range(x, y) and gameboard.get_tile(x, y).has_own_city(team):
                return True
    return False

def neighbouring_resource(tile: Tile) -> bool:
    for x in [tile.pos.x - 1, tile.pos.x + 1]:
        for y in [tile.pos.y - 1, tile.pos.y + 1]:
            if in_range(x, y) and gameboard.get_tile(x, y).has_resource():
                return True
    return False


def too_much_fuel(city_tile: CityTile) -> bool:
    """Check if city has enough fuel for the rest of the game"""
    city = gameboard.own_cities.get(city_tile.cityid)

    fuel_needed = city.get_light_upkeep() * night_moves_left()
    # if fuel_needed < city.fuel:
    #     actions.append(annotate.sidetext(f"City {city_tile.cityid} has enough fuel for the whole game"))
    return fuel_needed < city.fuel


def find_closest_city(pawn: Pawn, exclude_dir: List[DIRECTIONS] = None) -> Optional[Tile]:
    if exclude_dir is None:
        exclude_dir = []
    best_value = math.inf
    closest_city_tile = None
    for city_tile in gameboard.own_city_tiles:
        city = gameboard.get_city(city_tile.citytile.cityid)
        value = city_tile.pos.distance_to(pawn.pos) + city.fuel / (100 * city.get_light_upkeep())
        if (
            value < best_value
            and pawn.pos.direction_to(city_tile.pos) not in exclude_dir
            and pawn.team == city_tile.team
            and not too_much_fuel(city_tile.citytile)
        ):
            best_value = value
            closest_city_tile = city_tile
    if closest_city_tile is not None and can_move_to(pawn, pawn.pos.direction_to(closest_city_tile.pos)):
        return closest_city_tile
    elif closest_city_tile is not None:
        return find_closest_city(pawn, [*exclude_dir, pawn.pos.direction_to(closest_city_tile.pos)])


def cities_have_enough_foul(pawn: Pawn) -> bool:
    # is not night so can assume fuel needed is for 10 moves
    closest_city_tile = find_closest_city(pawn)
    if closest_city_tile is not None:
        distance = closest_city_tile.pos.distance_to(pawn.pos)
        city = gameboard.get_city(closest_city_tile.citytile.cityid)
        if distance < 5 and city is not None and city.get_light_upkeep() * 10 > city.fuel:
            return False
    return True

def city_fuel_levels(pawn: Pawn) -> Tuple[int, int]:
    radius = gameboard.width // 4
    amount_of_fuel = 0
    fuel_needed = 0
    for x in range(pawn.pos.x - radius, pawn.pos.x + radius + 1):
        for y in range(pawn.pos.y - radius, pawn.pos.y + radius + 1):
            if in_range(x, y) and gameboard.get_tile(x, y).has_city():
                city = gameboard.own_cities.get(gameboard.get_tile(x, y).citytile.cityid)
                if city is not None:
                    fuel_needed += city.get_light_upkeep() * 5 / (1 + pawn.pos.distance_to(Position(x, y)))
                    amount_of_fuel += city.fuel
    return amount_of_fuel, fuel_needed


def distance_to_nearest_city(pawn: Pawn) -> int:
    closest_dist = 10000
    for tile in gameboard.own_city_tiles:
        dist = tile.pos.distance_to(pawn.pos)
        if dist < closest_dist and pawn.team == tile.team and not too_much_fuel(tile.citytile):
            closest_dist = dist
    return int(closest_dist)


def distance_to_nearest_empty_tile(pawn: Pawn) -> int:
    closest_dist = math.inf
    for tile in gameboard.tiles:
        dist = tile.pos.distance_to(pawn.pos)
        if dist < closest_dist and not tile.has_city() and not tile.has_resource():
            closest_dist = dist
    return int(closest_dist)


def cities_fuel_amount(player: Player, pawn: Pawn) -> Tuple[int, int, int]:
    # first check the proximity for amount of foul
    radius = gameboard.width // 4
    amount_of_fuel = 0
    amount_of_fuel_with_all_resources = 0
    for x in range(pawn.pos.x - radius, pawn.pos.x + radius + 1):
        for y in range(pawn.pos.y - radius, pawn.pos.y + radius + 1):
            if in_range(x, y) and gameboard.get_tile(x, y).has_resource():
                resource = gameboard.get_tile(x, y).resource
                if has_access_to_resource(resource, player):
                    amount_of_fuel += resource.amount
                amount_of_fuel_with_all_resources += resource.amount
    amount_of_fuel_needed = 0
    for x in range(pawn.pos.x - radius, pawn.pos.x + radius + 1):
        for y in range(pawn.pos.y - radius, pawn.pos.y + radius + 1):
            if in_range(x, y) and gameboard.get_tile(x, y).has_city():
                city = gameboard.own_cities.get(gameboard.get_tile(x, y).citytile.cityid)
                if city is not None:
                    amount_of_fuel_needed += city.get_light_upkeep() * night_moves_left()

    return amount_of_fuel, amount_of_fuel_with_all_resources, amount_of_fuel_needed


def in_range(x: int, y: int):
    return x >= 0 and y >= 0 and x < gameboard.width and y < gameboard.height


def in_range_pos(pos: Position):
    return in_range(pos.x, pos.y)


def can_move_to(own_pawn: Pawn, direction: DIRECTIONS) -> bool:
    """
    Check if the unit `ownUnit` can move in direction `dir` 1 step.
    """

    if direction == DIRECTIONS.CENTER:  # can always stay put
        return True
    end_position = Position.translate(own_pawn.pos, direction, 1)
    tile = gameboard.get_tile_by_pos(end_position)
    for pawn in gameboard.pawns:
        if pawn.next_move.x == end_position.x and pawn.next_move.y == end_position.y:
            if not tile.has_city() or tile.team != own_pawn.team:
                return False
        elif tile.has_city() and tile.team != own_pawn.team:
            return False
    actions.append(annotate.line(own_pawn.pos.x, own_pawn.pos.y, end_position.x, end_position.y))
    return True


def update_move(pawn: Pawn, tile: Tile) -> None:
    """
    Update the `next_move` property of the pawn. Needed for collision checks
    """
    end_position = Position.translate(pawn.pos, pawn.pos.direction_to(tile.pos), 1)
    pawn.next_move = end_position


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


def should_build_city(player: Player, pawn: Pawn) -> bool:
    if pawn.get_cargo_space_left() != 0:
        return False
    score = 0

    # first check if cities in vicinites have enough fuel
    fuel_amount, fuel_needed = city_fuel_levels(pawn)
    score -= 100 * fuel_needed / (fuel_amount + 1)

    # second check if not enough fuel to support city
    fuel_amount, all_fuel_amount, fuel_needed = cities_fuel_amount(player, pawn)
    score += (all_fuel_amount - fuel_needed + fuel_amount - fuel_needed) / 2

    # third check how long to an empty tile
    distance = distance_to_nearest_empty_tile(pawn)
    score -= 100 * distance

    # fourth check long to next city
    distance = distance_to_nearest_city(pawn)
    score += 100 * distance

    # fifth check if it is night
    score -= 10000 if is_night() else 0

    return score > 0


def agent(observation, configuration):
    global game_state
    global actions
    global gameboard
    global moveCount
    global wood_position
    global coal_position

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
                    update_move(pawn, wood_tile)
                    actions.append(pawn.move(pawn.pos.direction_to(wood_tile.pos)))
                    if wood_position.distance_to(pawn.pos) <= 1:
                        wood_position = None
                else:
                    logging.info(f"Unit {pawn.pawn_id} tried to move to wood tile, in move {moveCount}, but couldnt!")
            elif index == 0 and coal_position is not None:
                coal_tile = move_to_position(pawn, coal_position)
                if coal_tile is not None:
                    update_move(pawn, coal_tile)
                    actions.append(pawn.move(pawn.pos.direction_to(coal_tile.pos)))
                    if coal_position.distance_to(pawn.pos) <= 1:
                        coal_position = None
                else:
                    logging.info(f"Unit {pawn.pawn_id} tried to move to coal tile, in move {moveCount}, but couldnt!")
            elif should_build_city(player, pawn):
                # try and build city
                closest_empty_tile = find_closest_empty_tile(pawn)
                if pawn.can_build(game_state.map):
                    actions.append(pawn.build_city())
                elif closest_empty_tile is not None and can_move_to(
                    pawn, pawn.pos.direction_to(closest_empty_tile.pos)
                ):
                    update_move(pawn, closest_empty_tile)
                    actions.append(pawn.move(pawn.pos.direction_to(closest_empty_tile.pos)))
                else:
                    logging.info(f"Unit {pawn.pawn_id} tried to build city, in move {moveCount}, but couldnt!")
            elif pawn.get_cargo_space_left() > 0 and (
                cities_have_enough_foul(pawn) or pawn.get_cargo_space_left() == 100
            ):
                # if the unit is a worker and we have space in cargo, lets find the nearest resource tile and try to mine it
                closest_resource_tile = find_closest_resource_tile(player, pawn)
                if closest_resource_tile is not None:
                    update_move(pawn, closest_resource_tile)
                    actions.append(pawn.move(pawn.pos.direction_to(closest_resource_tile.pos)))
                else:
                    logging.info(
                        f"Unit {pawn.pawn_id} tried to move to resource tile, in move {moveCount}, but couldnt!"
                    )
            else:
                # if unit is a worker and there is no cargo space left, and we have cities, lets return to them
                if len(player.cities) > 0:
                    closest_city_tile = find_closest_city(pawn)
                    if closest_city_tile is not None:
                        update_move(pawn, closest_city_tile)
                        actions.append(pawn.move(pawn.pos.direction_to(closest_city_tile.pos)))
                    else:
                        logging.info(f"Unit {pawn.pawn_id} tried to move to city, in move {moveCount}, but couldnt!")
    for _, city in player.cities.items():
        for tile in city.citytiles:
            if (
                tile.can_act()
                and player.city_tile_count > cart_count + worker_count
                and (worker_count < HARD_UNIT_LIMIT or player.researched_uranium())
            ):
                actions.append(tile.build_worker())
                worker_count += 1
            elif tile.can_act() and not player.researched_uranium():
                actions.append(tile.research())

    moveCount += 1
    return actions
