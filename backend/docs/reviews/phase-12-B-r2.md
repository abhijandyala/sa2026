CHANGES NEEDED

medium | fieldshift/planner/wheat_path.py:271 | Comparison validation accepts unknown crops and invalid crop roles (e.g. winter_wheat as cover), returning 200/complete | Validate comparison crop IDs and roles before replay; return typed issues.

medium | fieldshift/planner/wheat_path.py:195 | Omitting production_system silently drops three wheat checks marked unknown, including the Hessian fly check | Expose unknown checks with missing_inputs; add an omitted-system regression test.