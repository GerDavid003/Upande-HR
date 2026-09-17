# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Case Management card on the Tenure workspace.

Tenure is shipped by HRMS (`hrms/hr/workspace/tenure/tenure.json`, module HR), so the
card cannot live in that file — it is not ours to edit, and an HRMS upgrade would drop
the change on the next pull.

It is not a one-shot patch either. `import_file` re-imports a workspace whenever the
shipped JSON's hash changes, which replaces the Workspace row wholesale. A patch runs
once, so the card would survive until the next HRMS upgrade and then vanish silently.
Running from after_migrate instead re-asserts the card after any such re-import, and
the idempotency guard makes the repeat runs free.
"""

import json

import frappe

WORKSPACE = "Tenure"
CARD_LABEL = "Case Management"
CARD_COLUMN_WIDTH = 4
# The content block id only has to be unique within the workspace; a fixed value keeps
# repeat runs from piling up near-identical blocks.
CONTENT_BLOCK_ID = "upandeHrCaseMgmt"

CARD_LINKS = (
	("Disciplinary Case", "DocType"),
	("Disciplinary Warning", "DocType"),
)


def add_case_management_card():
	"""Append the Case Management card to Tenure, skipping if it is already there."""
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	# after_migrate runs once doctypes have synced, but guard anyway: a link pointing at
	# a missing DocType renders a dead card.
	missing = [name for name, link_type in CARD_LINKS
			   if link_type == "DocType" and not frappe.db.exists("DocType", name)]
	if missing:
		frappe.log_error(
			title="upande_hr: Tenure card skipped",
			message=f"Missing DocTypes: {', '.join(missing)}",
		)
		return

	workspace = frappe.get_doc("Workspace", WORKSPACE)

	if any(row.type == "Card Break" and row.label == CARD_LABEL for row in workspace.links):
		return

	workspace.append("links", {
		"type": "Card Break",
		"label": CARD_LABEL,
		"link_count": len(CARD_LINKS),
		# No link_type: it is a Select, so Frappe stores the first option ("DocType")
		# whatever we pass. Harmless - a Card Break carries no target and the renderer
		# keys off type, not link_type - but it is why this row reads "DocType" in the
		# database while the break rows HRMS imports from JSON read null.
		"hidden": 0,
		"onboard": 0,
		"is_query_report": 0,
	})
	for label, link_type in CARD_LINKS:
		workspace.append("links", {
			"type": "Link",
			"label": label,
			"link_type": link_type,
			"link_to": label,
			"link_count": 0,
			"hidden": 0,
			"onboard": 0,
			"is_query_report": 0,
		})

	# The card only renders if a matching block exists in `content`, and card_name has
	# to equal the Card Break label exactly or the card comes out empty.
	content = json.loads(workspace.content or "[]")
	already_there = any(
		block.get("type") == "card" and (block.get("data") or {}).get("card_name") == CARD_LABEL
		for block in content
	)
	if not already_there:
		content.append({
			"id": CONTENT_BLOCK_ID,
			"type": "card",
			"data": {"card_name": CARD_LABEL, "col": CARD_COLUMN_WIDTH},
		})
		workspace.content = json.dumps(content)

	workspace.save(ignore_permissions=True)
