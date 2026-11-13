Follow-up research request: Field Shift catalogs, v2 additions

Context: you supplied crops.csv, crop_rules.csv, and fertilizers.csv (v1) for a North Carolina Piedmont (Union County) crop-rotation planner. We need a small set of additional rows in the SAME schemas. Return only new or corrected rows, as CSV with header rows, in two files: crops_v2_additions.csv and crop_rules_v2_additions.csv.

crop_rules.csv header (exact):
rule_id,crop_id,region,rule_type,growth_stage,management_action,cultivar_or_maturity_group,production_system,previous_crop_id,next_crop_id,window_start_mm_dd,window_end_mm_dd,condition_key,operator,value_min,value_max,value_text,unit,exposure_duration,exposure_unit,suitability,applies_when,guidance,source_title,source_url,source_locator,verified_date

Use the same rules as v1:
- UTF-8, one independently sourced finding per row.
- IDs and condition keys are lowercase snake_case.
- Dates are MM-DD; verified_date is YYYY-MM-DD.
- operator is one of lt, lte, gt, gte, eq, between. For between, put both inclusive bounds in value_min/value_max.
- suitability is preferred, acceptable, caution, avoid, unknown, or blank for descriptive rows.
- Blank means unknown or inapplicable; never write 0 for unknown.
- Qualitative findings go in value_text/guidance with the numeric fields blank.
- Every row needs source_title, source_url (prefer NC State Extension / NCSU, then USDA, VCE, SARE), and a specific source_locator (page, table, or section).
- Use "NC Piedmont" when the source is Piedmont-specific. Otherwise state the actual region and do not generalize.
- crop_id values that already exist: field_corn, soybean, cereal_rye, crimson_clover, winter_wheat.
- New rule_ids must not collide with v1. Use prefixes ww_ (wheat), sb_ (soybean), fc_ (corn).

Needed rows, highest priority first:

1. Winter wheat for grain (crop_id winter_wheat), NC Piedmont:
   a. Planting window: preferred and acceptable date ranges (rule_type planting_window, management_action plant). Include any Hessian fly / first-freeze based guidance as a separate row.
   b. Harvest timing: the typical grain harvest date range in the Piedmont (rule_type growth_duration, growth_stage harvest, management_action harvest, with window dates if published).
   c. Seeding rate or depth only if NC State gives them in the same source. This is optional.
   d. Any rotation_compatibility rows for wheat after soybean (previous_crop_id soybean).

2. Double-crop soybean after wheat (crop_id soybean, production_system double_crop, previous_crop_id winter_wheat):
   a. Planting window after wheat harvest, as dates, plus the yield-decline guidance for later planting dates (rule_type planting_window).
   b. Recommended maturity group range for double-crop in NC (keep consistent with v1 sb_rc_03, which says to avoid MG < 4).
   c. Row spacing or seeding rate adjustment for late planting, if NC State publishes one.

3. Harvest timing for the cash crops, NC Piedmont (needed to place the winter window):
   a. Field corn grain: typical harvest date range and/or planting-to-maturity days by relative maturity. Piedmont-specific if possible. v1 only has Hertford County (fc_gd_01).
   b. Full-season soybean (MG 5 to early 7 in NC): typical harvest date range or R8 timing by planting date.

4. Fix two v1 rows: fc_nut_01 and sb_nut_01 have a blank verified_date. Re-verify them and return the corrected rows with all columns filled.

5. If available (lower priority):
   a. A published definition of a "heavy rain day" or "heavy precipitation event" used for erosion or soil-loss context in NC or the Southeast US (for example, a daily inch threshold, or the R95p climate index). Return it as a row with crop_id blank and rule_type weather_tolerance; we will move it to a reference file. Include the source and locator.
   b. Any NC State guidance on cereal rye establishment time (days from seeding to meaningful ground cover) in the Piedmont.

If a fact cannot be verified from a citable source, do not invent it. List it at the end under "Not found", with what you searched.
