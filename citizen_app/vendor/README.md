# Files from other projects

The citizen app loads nothing from other servers. The service allows a citizen's browser to fetch only from the
service itself (the `Content-Security-Policy` header in `drone_vision/service.py`), so no other company learns who
opens the app, and the app keeps working when those servers do not answer. What the app uses from other projects is
therefore stored here: the library that draws the map, the letter shapes for names on the map, the stylesheet that
gives the app its look, and the icons. Every file is as its project published it, except one, from which one rule was
taken out (see "The one file that is not as published").

| File | What it is | Licence |
|---|---|---|
| `maplibre-gl.js`, `maplibre-gl.css` | MapLibre GL JS 4.7.1: draws the map | BSD 3-Clause, in `maplibre-gl.LICENSE.txt` |
| `fonts/noto-sans-regular/0-255.pbf`, `256-511.pbf` | Noto Sans Regular as map letter shapes: Latin letters, including the Turkish ones | SIL Open Font License 1.1, in `fonts/OFL.txt` |
| `framework7.min.css` | Framework7 9.3.0, its stylesheet only, without its script: how buttons, lists, the white blocks and the switch between the two lists look | MIT, in `framework7.LICENSE.txt` |
| `ionicons/*.svg` | Ionicons 8.1.0, thirteen of its outline drawings: the icons | MIT, in `ionicons/LICENSE.txt` |

Names in other scripts (Greek, Arabic) are not written on the map, because their letter shapes are not here. The
panel and the lists show every name: they use the phone's own fonts.

## Where each file came from

MapLibre and the letter shapes were downloaded on 12 November 2026, Framework7 and Ionicons on 15 November 2026.

| File | Address | SHA-256 |
|---|---|---|
| `maplibre-gl.js` | `https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js` | `be9633c4d870e26fb37f1cfe5c5a77181667114003ea16207ac7850d8da8add1` |
| `maplibre-gl.css` | `https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css` | `576b085fdd9487a65a19215328c1e086c07ce5bf6da09b666b3806d3d008dae9` |
| `maplibre-gl.LICENSE.txt` | `https://unpkg.com/maplibre-gl@4.7.1/LICENSE.txt` | `ee5fc05a0677eaf69601d2c7db0d9ecd6cc27c3abc1d0733bc9ed34707cf8ef2` |
| `fonts/noto-sans-regular/0-255.pbf` | `https://protomaps.github.io/basemaps-assets/fonts/Noto%20Sans%20Regular/0-255.pbf` | `62c6d49b15fa836eb6aa45e259c7ca6762f44b011b09e47776efbe4a6db1b397` |
| `fonts/noto-sans-regular/256-511.pbf` | `https://protomaps.github.io/basemaps-assets/fonts/Noto%20Sans%20Regular/256-511.pbf` | `2eca7561f9f566bcacfda5dd04fb5880baec1328ec0f5484678289a13994de8a` |
| `fonts/OFL.txt` | `https://raw.githubusercontent.com/protomaps/basemaps-assets/main/fonts/OFL.txt` | `7713cfc8e3c36d5ec4aa3d6cffe7500a1b3310f8a86d914b8ea09c2a9dee7c2d` |
| `framework7.min.css` | `https://unpkg.com/framework7@9.3.0/framework7.min.css` | `5b0ea6a228abfcdd7b5ddb939ec2c0f200078a450e705c19fcfa6d7765826b90` |
| `framework7.LICENSE.txt` | `https://unpkg.com/framework7@9.3.0/LICENSE` | `1c115994b4470862e1fa6d694a326f5d745dd8e77027a5ab18e7c285b05fa59e` |
| `ionicons/alert-circle-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/alert-circle-outline.svg` | `38dd7f799e5a937dadcb77b34a49cae251417f161992ddb78dc9053e9ccf2f1e` |
| `ionicons/checkmark-circle-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/checkmark-circle-outline.svg` | `097d39e73465ab4920a07865c8b4163c049ab0aeafa35f44a12401446ba85e92` |
| `ionicons/chevron-down-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/chevron-down-outline.svg` | `e7c93986e0e1acef4f8c87f75407a06aad69a4231457c956983f06889304d56e` |
| `ionicons/chevron-forward-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/chevron-forward-outline.svg` | `859c42a34507364fa3a3689dec2e940f75ac35f0bfe1856437a743408ddbfeb9` |
| `ionicons/chevron-up-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/chevron-up-outline.svg` | `c9d145245834a54db3391a6581242b91d56994ee53364486c1f47e5addf35978` |
| `ionicons/close-circle-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/close-circle-outline.svg` | `ef414e5e2c1ff5a97c436fbd1af341fa24114cdded2a233c3ee6435b46912f23` |
| `ionicons/close-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/close-outline.svg` | `9b0157f1a27d431e6d933de10ac86d556251416d879536d8e246627407299a79` |
| `ionicons/cloud-offline-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/cloud-offline-outline.svg` | `095ae872bef1150b770d00cef291d5a6e62579a4d01b4e478e2b592f9cb8155e` |
| `ionicons/globe-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/globe-outline.svg` | `26c7b1386840b046255f18be9fbf156be39ade5c05da9918e756a7ea5e0a1f7e` |
| `ionicons/information-circle-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/information-circle-outline.svg` | `c4a5bbaaaa1e9155f5bafba8870f7547499458235a3e051c980aa3ffc524c185` |
| `ionicons/location-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/location-outline.svg` | `5a2a4f0c80a22757d5f211f5a72bc984203d518913bfe2fcc9e73c8462d6c8d8` |
| `ionicons/map-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/map-outline.svg` | `a89481cefdf55c9678d7358513cc66ec5b80ebd28fd49d7a925d66428cf5bd50` |
| `ionicons/megaphone-outline.svg` | `https://unpkg.com/ionicons@8.1.0/dist/svg/megaphone-outline.svg` | `739502b9ae85f9a6974a4626353767eef5e50dcd999e0a2bd400520ffc449bf9` |
| `ionicons/LICENSE.txt` | `https://unpkg.com/ionicons@8.1.0/LICENSE` | `c89dabc60b2e4e1a04b33bd7010b5a56bb4725ffe8c00d793a5ae009fbbfebd8` |

The two MapLibre files were also downloaded from jsDelivr (`https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/dist/`)
and were the same, byte for byte. Framework7 and Ionicons were taken from their packages on the npm registry
(`framework7-9.3.0.tgz`, `ionicons-8.1.0.tgz`) and then downloaded once more, file by file, from the addresses above:
the same, byte for byte.

## The one file that is not as published

`framework7.min.css` is Framework7's file with one rule taken out: the `@font-face` rule that carries the library's
own icon font inside the stylesheet, as a `data:` address. The service lets a citizen's browser load a font only from
the service itself, so the browser refused that font every time the app opened and said so in its console, although
nothing in the app uses it. The app's icons are Ionicons' drawings, and the one arrow the library draws with its font
(at the end of a row that can be pressed) is drawn in `app.css` instead. Nothing else in the file was changed.

The published file has the SHA-256 `78b0095a07cd13d48aeef9d4ef57b52cc9634bf2eb279c80d747f74ea3172d53`. Taking the
rule out of it gives the file stored here, whose checksum is in the table above:

```
curl -sL https://unpkg.com/framework7@9.3.0/framework7.min.css | perl -0pe 's/\@font-face\{[^{}]*\}//' | shasum -a 256
```

A test (`tests/test_citizen_app.py`) keeps the stored stylesheet free of fonts, of files to fetch and of addresses.

## Checking and updating

To check that nothing here was changed, from this folder:

```
shasum -a 256 maplibre-gl.js maplibre-gl.css maplibre-gl.LICENSE.txt fonts/OFL.txt fonts/noto-sans-regular/*.pbf \
    framework7.min.css framework7.LICENSE.txt ionicons/*
```

To move to another MapLibre version: download the three files of that version from the addresses above, replace
them, update the version and the checksums in this file, and open the app once on a phone. `map.js` uses only the
public parts of MapLibre (`Map`, `Marker`, `Popup`, `NavigationControl`, `AttributionControl`, `LngLatBounds`).

To move to another Framework7 version: download its `framework7.min.css`, take the font rule out with the command
above, replace the file and its checksums here, and look at every screen of the app. The app uses the library
without its JavaScript, so three things that the script would do are written out by hand and have to be looked at
again: `index.html` names the look (`class="ios"` on `<html>`; the script would choose one for the device), `app.css`
gives the colours of the theme (worked out once with Framework7's own colour function) and says how a pressed button
and a pressed row look. `app.css` also draws the arrow at the end of a row, which the library draws with the font
that was taken out.

To add an icon: download its drawing from `https://unpkg.com/ionicons@8.1.0/dist/svg/<name>.svg` into `ionicons/`,
add its row to the table, and name it in `app.css`. A phone keeps every file of this folder, so a drawing the app
does not use is not stored here.
