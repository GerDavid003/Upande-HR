# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from upande_hr.setup.separation_types import seed_separation_types


def execute():
	"""Sites that already had upande_hr installed do not run after_install, so the
	Separation Types arrive through this patch instead."""
	seed_separation_types()
