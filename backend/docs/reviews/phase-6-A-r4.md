CHANGES NEEDED

medium | tests/api/test_api_wheat.py:154 | Test fails with KeyError: cross_calendar.double_crop has no cutoff_mm. | Remove this assertion; retain the own-window cutoff check against the frozen threshold on line 153.
Reply (A): fixed. At HEAD `cross_calendar.double_crop` carries `cutoff_mm` and the test passed, but B's uncommitted `wheat_path.py` drops it; the cutoff in `cross_calendar` is B's output, so the test no longer asserts it. The own-window cutoff is still checked against the frozen threshold (`double_crop.spring.cutoff_mm`).
