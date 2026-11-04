# Each developer reads sources from personal clones or samples

The dev workspace can read prod catalogs. Instead of every dev build reading prod sources directly, each developer creates their own Delta shallow clones (`<product>__<alias>__src_clone`) or small samples (`…__src_sample`) of the sources. A `dev_source_mode` variable (`prod` | `clone` | `sample`, default `clone`) selects which; prod ignores it. Personal copies cost little (shallow clones copy no data) and make sure no developer depends on a shared copy someone else might refresh.

## Consequences

- A shallow clone breaks once prod runs `VACUUM` and removes files the clone still references. `make clone-sources` re-creates them.
- Views can't be shallow-cloned. View sources are read from prod in every mode.
