CHANGES NEEDED

medium | fieldshift/catalogs/loader.py:303 | Crop-reference fix excludes only validation errors: an invalid crop verified_date removes the crop but leaves referencing rules usable. | Build usable_crop_ids via _usable(crops, issues, CROPS_FILE); add a regression test for parsing errors.