from typing import Callable, List, Optional
from lux.game import Game
from lux.game_objects import City, CityTile, Unit
from lux.game_map import DIRECTIONS, Cell, GameMap, Position


class Pawn:
    def __init__(self, unit: Unit):
        self.unit = unit
        self.next_move: Position = Position(self.unit.pos.x, self.unit.pos.y)
        self.team = self.unit.team
        self.pos = Position(self.unit.pos.x, self.unit.pos.y)
        self.pawn_id = self.unit.id

    @property
    def next_move(self) -> Position:
        return self._next_move

    @next_move.setter
    def next_move(self, pos: Position) -> None:
        self._next_move = pos

    def is_worker(self) -> bool:
        return self.unit.is_worker()

    def can_act(self) -> bool:
        return self.unit.can_act()

    def can_build(self, game_map: GameMap) -> bool:
        return self.unit.can_build(game_map)

    def get_cargo_space_left(self) -> int:
        return self.unit.get_cargo_space_left()

    def build_city(self) -> str:
        return self.unit.build_city()

    def move(self, direction: DIRECTIONS) -> str:
        return self.unit.move(direction)


class Tile:
    def __init__(self, cell: Cell) -> None:
        self.cell = cell
        self.resource = cell.resource
        self.pos = cell.pos
        self.team = 0 if cell.citytile is None else cell.citytile.team
        self.citytile: Optional[CityTile] = cell.citytile

    def has_resource(self) -> bool:
        return self.cell.has_resource()

    def has_city(self) -> bool:
        return self.cell.citytile is not None
    
    def has_own_city(self, team: int) -> bool:
        return self.cell.citytile and self.cell.citytile.team == team 


class GameBoard:
    def __init__(self, game_state: Game, observation) -> None:
        self.map = game_state.map
        self.width = self.map.width
        self.height = self.map.height
        self.tiles: List[Tile] = [Tile(self.map.get_cell(x, y)) for x in range(self.width) for y in range(self.height)]
        self.resource_tiles = list(filter(lambda tile: tile.has_resource(), self.tiles))
        self.city_tiles = list(filter(lambda tile: tile.has_city(), self.tiles))
        self.own_city_tiles = list(filter(lambda city_tile: city_tile.team == observation.player, self.city_tiles))
        self.enemy_city_tiles = list(filter(lambda city_tile: city_tile.team != observation.player, self.city_tiles))
        self.pawns = [Pawn(unit) for unit in [*game_state.players[0].units, *game_state.players[1].units]]
        self.own_pawns = list(filter(lambda pawn: pawn.team == observation.player, self.pawns))
        self.enemy_pawns = list(filter(lambda pawn: pawn.team != observation.player, self.pawns))
        self.own_cities = game_state.players[observation.player].cities
        self.enemy_cities = game_state.players[(observation.player + 1) % 2].cities

    def get_tile(self, x, y) -> Tile:
        return self.tiles[y + x * self.width]

    def get_tile_by_pos(self, pos: Position) -> Tile:
        return self.tiles[pos.y + pos.x * self.width]

    def annotate_city(self, city_id: str, function: Callable[[int, int], str]) -> List[str]:
        actions = []
        for city_tile in self.own_city_tiles:
            if city_id == city_tile.citytile.cityid:
                actions.append(function(city_tile.pos.x, city_tile.pos.y))
        return actions

    def get_city(self, city_id: str) -> Optional[City]:
        return self.own_cities.get(city_id)
    