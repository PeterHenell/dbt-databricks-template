# Personal environments are schemas in the team catalog

Developers cannot create catalogs in the dev workspace: each team gets one team catalog, shared by all of the team's data products. Isolation is therefore done with schemas named `<product>__<alias>__<layer>` (e.g. `orders__pehe__staging`), produced by a single `generate_schema_name` override that returns plain `<layer>` in prod. The double underscore keeps the parts separable even when product names or aliases contain `_`, so cleanup can safely drop everything with one developer's prefix.

## Consequences

- Teammates can read each other's personal environments. The platform team grants this at the team catalog level; the template does not manage grants.
- Alias collisions are not checked automatically. Teams are small; if two aliases collide, one developer edits the `schema` value in their `profiles.yml`.
