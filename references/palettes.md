# Palettes

Every `.pxg` sheet declares at most 16 colors. With `palette: db32`, each declared hex must be one of the 32 below (DawnBringer 32, public domain — the most widely used general-purpose pixel-art palette). Pick 4–12 for a tile or item, 8–16 for a character.

| # | hex | reads as |
|---|---|---|
| 0 | `#000000` | black |
| 1 | `#222034` | near-black blue (outlines on dark art) |
| 2 | `#45283c` | dark plum |
| 3 | `#663931` | dark brown |
| 4 | `#8f563b` | brown |
| 5 | `#df7126` | orange |
| 6 | `#d9a066` | tan |
| 7 | `#eec39a` | light tan / skin |
| 8 | `#fbf236` | yellow |
| 9 | `#99e550` | light green |
| 10 | `#6abe30` | green |
| 11 | `#37946e` | teal green |
| 12 | `#4b692f` | dark green |
| 13 | `#524b24` | olive |
| 14 | `#323c39` | dark slate |
| 15 | `#3f3f74` | navy |
| 16 | `#306082` | dark blue |
| 17 | `#5b6ee1` | blue |
| 18 | `#639bff` | light blue |
| 19 | `#5fcde4` | cyan |
| 20 | `#cbdbfc` | pale blue |
| 21 | `#ffffff` | white |
| 22 | `#9badb7` | light grey |
| 23 | `#847e87` | grey |
| 24 | `#696a6a` | mid grey |
| 25 | `#595652` | dark grey |
| 26 | `#76428a` | purple |
| 27 | `#ac3232` | red |
| 28 | `#d95763` | pink red |
| 29 | `#d77bba` | pink |
| 30 | `#8f974a` | moss |
| 31 | `#8a6f30` | dark gold |

## Ramps that work (light → dark)

- grass: `#99e550` → `#6abe30` → `#4b692f` → `#323c39`
- dirt / wood: `#eec39a` → `#d9a066` → `#8f563b` → `#663931`
- stone: `#cbdbfc` → `#9badb7` → `#847e87` → `#595652`
- water: `#cbdbfc` → `#5fcde4` → `#639bff` → `#306082`
- skin: `#eec39a` → `#d9a066` → `#8f563b`
- cloth red: `#d95763` → `#ac3232` → `#45283c`
- cloth blue: `#639bff` → `#5b6ee1` → `#3f3f74`
- outline: `#222034` on most art, `#000000` only when the art is very bright

Shade by moving along a ramp, never by mixing in black or white.

## `palette: custom`

Used by `import` (colors come from the source PNG) and by users who ship their own palette. Same 16-color cap, no membership check.
