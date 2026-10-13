### Upande Hr

HR customisations for Upande

### Dependencies outside required_apps (mgp branch only)

These Employee Custom Fields assume apps this app does not declare. That's fine on
`mgp`, which serves Marginpar only, but don't merge them into a shared branch:

- `Employee-custom_block` links to **Block**, a doctype owned by `upande_propagation`.
  Without that app the fixture still imports, because Frappe skips the link-target
  check during fixture sync, but the field links to a doctype that doesn't exist and
  breaks on use.
- `Employee-custom_unit` and `Employee-custom_block` are anchored on
  `custom_greenhouse`, an Employee field shipped by `upande_agriculture`.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app upande_hr
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/upande_hr
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
