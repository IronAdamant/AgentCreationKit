"""What differs between Bethesda games, in one place. Everything else in ack reads it from here.

Pick the game with "game" in config.local.json (default "fo4"). To support another game, add a profile and
mark what has been checked against the real tools: `verified` lists the areas used on real work with that game.
Values not yet tried in practice are best knowledge (xEdit's own rules), so treat a first run with care.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Game:
    key: str
    name: str
    masters: tuple[str, ...]            # official masters in load order (the base game and its DLC)
    xedit_exe: str                      # xEdit's dedicated exe name; any other name needs xedit_mode
    xedit_mode: str                     # xEdit's game switch, e.g. -fo4 (for a generic xEdit.exe)
    exe: str = ''                       # the game's exe in its folder
    ck_exe: str = 'CreationKit.exe'
    ck_window_class: str | None = None  # the CK main window's class; None = ack.ck not checked for this game
    my_games: str = ''                  # folder under Documents/My Games
    custom_ini: str = ''                # the user ini that overrides the game's defaults
    light_plugins: bool = True          # ESL-flagged plugins exist
    light_min_extended: tuple[float, int] | None = None  # (HEDR version, lowest object ID) of the extended range
    papyrus_sources: str = ''           # the vanilla script sources, under Data (unpacked by the CK)
    papyrus_flags: str = ''             # the compiler's flags file, in papyrus_sources
    papyrus_release: tuple[str, ...] = ()   # compiler options for a release build
    ba2_version: int | None = None      # the BA2 version `ack ba2 pack` stamps; None = ack does not pack this game
    verified: tuple[str, ...] = field(default_factory=tuple)

    def light_range(self, hedr_version: float) -> tuple[int, int]:
        """Object IDs a light plugin (ESL flag) may use, for its header (HEDR) version."""
        ext = self.light_min_extended
        if ext and hedr_version >= ext[0] - 1e-6:
            return ext[1], 0xFFF
        return 0x800, 0xFFF


GAMES = {g.key: g for g in [
    Game('fo4', 'Fallout 4',
         ('Fallout4.esm', 'DLCRobot.esm', 'DLCworkshop01.esm', 'DLCCoast.esm', 'DLCworkshop02.esm',
          'DLCworkshop03.esm', 'DLCNukaWorld.esm'),
         'FO4Edit.exe', '-fo4', exe='Fallout4.exe', ck_window_class='Creation Kit', my_games='Fallout4',
         custom_ini='Fallout4Custom.ini',
         # Sandbox Room (HEDR 1.0) uses 0x5C1-0xF79 and loads fine in game.
         light_min_extended=(1.0, 0x001),
         papyrus_sources='Scripts/Source/Base', papyrus_flags='Institute_Papyrus_Flags.flg',
         papyrus_release=('-release', '-final'),
         # The next-gen Archive2 writes version 8, which the old-gen game (1.10.163) skips; the layout is the
         # same and every PC version reads 1.
         ba2_version=1,
         verified=('xedit', 'ck', 'plugin', 'papyrus-log', 'papyrus', 'ba2')),
    Game('sse', 'Skyrim Special Edition',
         ('Skyrim.esm', 'Update.esm', 'Dawnguard.esm', 'HearthFires.esm', 'Dragonborn.esm'),
         'SSEEdit.exe', '-sse', exe='SkyrimSE.exe', my_games='Skyrim Special Edition', custom_ini='SkyrimCustom.ini',
         papyrus_sources='Source/Scripts', papyrus_flags='TESV_Papyrus_Flags.flg', papyrus_release=('-optimize',),
         # HEDR 1.71 (game 1.6.1130 and later) opens object IDs below 0x800, per xEdit.
         light_min_extended=(1.71, 0x001)),
]}


def get(key: str) -> Game:
    try:
        return GAMES[key.lower()]
    except KeyError:
        raise SystemExit(f'unknown game {key!r}: one of {", ".join(GAMES)} (add a profile in ack/games.py)')
