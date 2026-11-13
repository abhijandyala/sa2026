CHANGES NEEDED

medium | fieldshift/field/location.py:103 | Coarse polygon rejects the [Census point for Hot Springs, NC](https://tigerweb.geo.census.gov/tigerwebmain/Files/acs26/tigerweb_acs26_incplace_nc.html) as unsupported_location. | Use an accurate offline boundary and add this regression.

medium | fieldshift/field/location.py:255 | Corrupt weather-cache manifests can raise uncaught KeyError, producing 500s. | Validate manifest fields and treat malformed caches as unavailable; test with daily.parquet present.

medium | fieldshift/field/evidence.py:98 | Evidence conversion ignores units: water_table_depth_in=10 with unit=cm becomes 10 inches. | Convert compatible units or reject mismatches.

medium | fieldshift/field/routes.py:60 | Missing lat/lon produces FastAPI’s default 422 without required metadata. | Return typed invalid_input responses with metadata; test missing parameters.