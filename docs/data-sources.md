# ORCA Data Sources Reference

| Provider | Description | Access Method | Key Variables | License / Limits |
|---|---|---|---|---|
| **Open-Meteo Marine API** | Live marine weather & short-term forecasts | Free REST API (no key required for reasonable rate) | Wave height, wave period, wave direction, ocean currents, SST, wind speed | Non-commercial attribution / Open data |
| **NOAA IBTrACS** | Historical tropical cyclone tracks (Global & North Indian Ocean / Arabian Sea) | CSV / NetCDF download & sync script | Storm positions, central pressure, maximum sustained wind, storm category | Public Domain (NOAA) |
| **GDACS (Global Disaster Alert and Coordination System)** | Multi-hazard alerts (Cyclones, Floods, Tsunamis) | RSS / GeoJSON / REST | Disaster footprints, alert levels (Red/Orange/Green), event dates | Open data (UN/EC) |
| **OpenStreetMap / Overpass API** | Coastal boundaries, settlements, ports, emergency infrastructure | Overpass QL / GeoJSON query | Administrative boundaries, populated places, maritime facilities | ODbL (OpenStreetMap contributors) |
| **WorldPop** | High-resolution gridded population estimates | GeoTIFF / Processed zonal stats | Estimated resident population count per grid cell | CC BY 4.0 |
| **Protected Planet / WDPA** | Marine Protected Areas (MPAs) & coastal conservation zones | Shapefile / GeoJSON extracts | MPA boundaries, IUCN category, designation year | UNEP-WCMC (Non-commercial research) |

## Data Ingestion Rules
1. Never commit raw downloaded GeoTIFFs or large archives to Git.
2. Ingestion scripts must be idempotent (`scripts/import_*.py`).
3. Always store timestamps in UTC and coordinates in WGS84.
