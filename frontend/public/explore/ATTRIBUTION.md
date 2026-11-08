# Explore assets

See `sources.json` for source URLs and NASA GLB SHA-256 checksums.

The full atlas and dedicated 2D thumbnails are documented in `atlas-credits.json`, `thumbnails/manifest.json`, and [the current integration guide](../../EXPLORE_3D_HANDOFF.md). Keep both source manifests and this attribution file with the runtime assets. The original-five entries below remain applicable; the expanded assets are credited here:

- `constellation-*.glb`, constellation SVGs, Messier positions/names and derived thumbnails: [d3-celestial / Olaf Frohn](https://github.com/ofrohn/d3-celestial), with the bundled `d3-celestial-LICENSE.txt` (BSD-3-Clause). Constellation figures illustrate angular patterns, not physical connections or IAU region borders. Partial WNY visibility is a geometric selection rule.
- HYG-derived named-star positions, colors and constellation-member matching: David Nash / Astronexus, [HYG v4.0](https://github.com/astronexus/HYG-Database), [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Changes include bright-star/declination selection, angular projection, enlarged stars, schematic depth, GLB packaging, and 2D layout projection. Retain attribution and share-alike terms for derived catalog layouts, including applicable constellation and star/cluster thumbnails.
- `moon-color.jpg` and the texture embedded in `moon.glb` and `thumbnails/moon.svg`: [NASA Scientific Visualization Studio CGI Moon Kit](https://svs.gsfc.nasa.gov/4720/), LRO/LROC, NASA/GSFC/Arizona State University, Ernie Wright. The globe/thumbnail uses the surface mosaic for an educational close-up; lighting/orientation are not a selected-time phase prediction.
- Other new planetary geometry/surfaces, enhanced stellar halos, nebula clouds, illustrative galaxy populations/arms, and original 2D planet/star/galaxy art: Pleiades, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), subject to the separately credited source data above. These are code-generated educational illustrations, not resolved star surfaces or measured 3D gas/dust reconstructions.
- `thumbnails/<stable-object-id>.svg`: 263 self-contained 400 x 300 card previews, generated separately from the photographic detail references. Original vector art, projected catalog layouts, and lunar imagery retain the corresponding credits/licenses above. The thumbnail manifest maps IDs to files; model filenames can differ from those IDs.

- `saturn.glb`, `jupiter.glb`: NASA Visualization Technology Applications and Development (VTAD), unchanged downloads from the linked NASA resource pages. Acknowledge NASA; [media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/). No endorsement implied.
- `saturn.jpg`: NASA/JPL-Caltech/Space Science Institute, Cassini reference image from the NASA Saturn page.
- `jupiter.jpg`: NASA, reference image from the NASA Jupiter page.
- `pleiades.jpg`: NASA/JPL-Caltech/UCLA, WISE infrared observation.
- `andromeda.jpg`: NASA/JPL-Caltech, GALEX ultraviolet observation.
- `star-catalog.json`, `pleiades.glb`: adapted from David Nash / Astronexus, HYG v4.0, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). [Catalog and field definitions](https://github.com/astronexus/HYG-Database/blob/main/hyg/README.md). Changes: subset selection, J2000 angular projection, schematic depth, enlarged radii, GLB packaging. Derived subset/model are released under CC BY-SA 4.0. They are not a measured 3D cluster reconstruction.
- `vega-illustration.glb`, `vega.svg`, `andromeda-illustration.glb`: original Pleiades educational illustrations, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Not resolved star imagery or measured galaxy geometry.
